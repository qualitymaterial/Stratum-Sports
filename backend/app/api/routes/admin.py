import csv
import io
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import String, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_permission, require_admin_user
from app.core.admin_roles import (
    PERMISSION_BILLING_WRITE,
    PERMISSION_ADMIN_READ,
    PERMISSION_OPS_TOKEN_WRITE,
    PERMISSION_PARTNER_API_WRITE,
    PERMISSION_USER_PASSWORD_RESET_WRITE,
    PERMISSION_USER_ROLE_WRITE,
    PERMISSION_USER_STATUS_WRITE,
    PERMISSION_USER_TIER_WRITE,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    generate_password_reset_token,
    hash_password_reset_token,
    verify_password,
)
from app.models.admin_audit_log import AdminAuditLog
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.api_partner_key import ApiPartnerKey
from app.models.cross_market_divergence_event import CrossMarketDivergenceEvent
from app.models.cycle_kpi import CycleKpi
from app.models.password_reset_token import PasswordResetToken
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.ops import (
    AdminBillingMutationOut,
    AdminBillingMutationRequest,
    AdminBillingSubscriptionOut,
    AdminOutcomesReportOut,
    AdminApiPartnerEntitlementOut,
    AdminApiPartnerEntitlementUpdateOut,
    AdminApiPartnerEntitlementUpdateRequest,
    AdminApiPartnerKeyIssueOut,
    AdminApiPartnerKeyIssueRequest,
    AdminApiPartnerKeyListOut,
    AdminApiPartnerKeyMutationRequest,
    AdminApiPartnerKeyOut,
    AdminApiPartnerKeyRevokeOut,
    AdminApiPartnerKeyRotateRequest,
    AdminOpsServiceTokenIssueOut,
    AdminOpsServiceTokenIssueRequest,
    AdminOpsServiceTokenListOut,
    AdminOpsServiceTokenMutationRequest,
    AdminOpsServiceTokenOut,
    AdminOpsServiceTokenRevokeOut,
    AdminOpsServiceTokenRotateRequest,
    AdminUserBillingOverviewOut,
    AdminUserActiveUpdateOut,
    AdminUserActiveUpdateRequest,
    AdminAuditLogItemOut,
    AdminAuditLogListOut,
    AdminOverviewOut,
    AdminUserPasswordResetOut,
    AdminUserPasswordResetRequest,
    AdminUserSearchItemOut,
    AdminUserSearchListOut,
    AdminUserRoleUpdateOut,
    AdminUserRoleUpdateRequest,
    AdminUserTierUpdateOut,
    AdminUserTierUpdateRequest,
    ConversionFunnelOut,
    CycleKpiOut,
    OperatorReport,
)
from app.services.admin_audit import write_admin_audit_log
from app.services.admin_outcomes import build_admin_outcomes_report
from app.services.operator_report import build_operator_report
from app.services.api_partner_entitlements import (
    DEFAULT_OVERAGE_UNIT_QUANTITY,
    get_api_partner_entitlement,
    get_or_create_api_partner_entitlement,
    serialize_api_partner_entitlement_for_audit,
)
from app.services.partner_api_keys import (
    issue_api_partner_key,
    list_api_partner_keys_for_user,
    revoke_api_partner_key,
    rotate_api_partner_key,
    serialize_api_partner_key_for_audit,
)
from app.services.ops_service_tokens import (
    get_ops_service_token,
    issue_ops_service_token,
    list_ops_service_tokens,
    revoke_ops_service_token,
    rotate_ops_service_token,
    serialize_ops_service_token_for_audit,
)
from app.services.stripe_service import (
    admin_cancel_user_subscription,
    admin_reactivate_user_subscription,
    admin_resync_user_subscription,
    get_latest_subscription_for_user,
)
from app.services.teaser_analytics import get_teaser_conversion_funnel

router = APIRouter()
settings = get_settings()
ADMIN_MUTATION_CONFIRM_PHRASE = "CONFIRM"
OUTCOMES_EXPORT_MAX_ROWS = 10_000
DIVERGENCE_EXPORT_MAX_ROWS = 10_000
logger = logging.getLogger(__name__)


def _require_step_up_auth(
    admin_user: User,
    step_up_password: str,
    confirm_phrase: str,
    mfa_code: str | None = None,
) -> None:
    if confirm_phrase.strip().upper() != ADMIN_MUTATION_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation phrase must be '{ADMIN_MUTATION_CONFIRM_PHRASE}'",
        )
    if not admin_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step-up authentication unavailable for this admin account",
        )
    if not verify_password(step_up_password, admin_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up authentication failed",
        )
    # MFA verification when admin has MFA enabled
    if admin_user.mfa_enabled and admin_user.mfa_secret_encrypted:
        if not mfa_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required for step-up authentication",
            )
        from app.services.admin_mfa import verify_totp_code
        if not verify_totp_code(admin_user.mfa_secret_encrypted, mfa_code.strip()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )


def _raise_billing_error(exc: Exception) -> None:
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Billing operation failed: {exc}") from exc


def _resolve_expires_at(expires_in_days: int | None) -> datetime | None:
    if expires_in_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=expires_in_days)


async def _get_partner_key_for_user(db: AsyncSession, *, user_id: UUID, key_id: UUID) -> ApiPartnerKey:
    stmt = select(ApiPartnerKey).where(ApiPartnerKey.id == key_id, ApiPartnerKey.user_id == user_id)
    key = (await db.execute(stmt)).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API partner key not found")
    return key


def _normalize_optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_time_bucket_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    allowed = {"OPEN", "MID", "LATE", "PRETIP", "UNKNOWN", "INPLAY"}
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="time_bucket must be one of OPEN, MID, LATE, PRETIP, UNKNOWN, INPLAY",
        )
    if cleaned == "INPLAY" and not settings.time_bucket_expose_inplay:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INPLAY time_bucket is disabled in current configuration",
        )
    return cleaned


def _build_outcomes_filename(suffix: str, extension: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"admin-outcomes-{suffix}-{timestamp}.{extension}"


def _render_outcomes_csv(
    report: AdminOutcomesReportOut,
    *,
    table: Literal["summary", "by_signal_type", "by_market", "top_filtered_reasons"],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if table == "summary":
        writer.writerow(["metric", "current", "baseline", "delta"])
        summary_rows = [
            ("clv_samples", report.kpis.clv_samples, report.baseline_kpis.clv_samples, report.delta_vs_baseline.clv_samples_delta),
            ("positive_count", report.kpis.positive_count, report.baseline_kpis.positive_count, report.delta_vs_baseline.positive_count_delta),
            ("negative_count", report.kpis.negative_count, report.baseline_kpis.negative_count, report.delta_vs_baseline.negative_count_delta),
            ("clv_positive_rate", report.kpis.clv_positive_rate, report.baseline_kpis.clv_positive_rate, report.delta_vs_baseline.clv_positive_rate_delta),
            ("avg_clv_line", report.kpis.avg_clv_line, report.baseline_kpis.avg_clv_line, report.delta_vs_baseline.avg_clv_line_delta),
            ("avg_clv_prob", report.kpis.avg_clv_prob, report.baseline_kpis.avg_clv_prob, report.delta_vs_baseline.avg_clv_prob_delta),
            ("sent_rate", report.kpis.sent_rate, report.baseline_kpis.sent_rate, report.delta_vs_baseline.sent_rate_delta),
            ("stale_rate", report.kpis.stale_rate, report.baseline_kpis.stale_rate, report.delta_vs_baseline.stale_rate_delta),
            ("degraded_cycle_rate", report.kpis.degraded_cycle_rate, report.baseline_kpis.degraded_cycle_rate, report.delta_vs_baseline.degraded_cycle_rate_delta),
            ("alert_failure_rate", report.kpis.alert_failure_rate, report.baseline_kpis.alert_failure_rate, report.delta_vs_baseline.alert_failure_rate_delta),
            ("status", report.status, "baseline_comparison", report.status_reason),
        ]
        if len(summary_rows) > OUTCOMES_EXPORT_MAX_ROWS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV export row limit exceeded")
        for metric, current, baseline, delta in summary_rows:
            writer.writerow([metric, current, baseline, delta])
    elif table == "by_signal_type":
        writer.writerow(["signal_type", "count", "positive_rate", "avg_clv_line", "avg_clv_prob"])
        rows = report.by_signal_type
        if len(rows) > OUTCOMES_EXPORT_MAX_ROWS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV export row limit exceeded")
        for row in rows:
            writer.writerow([row.name, row.count, row.positive_rate, row.avg_clv_line, row.avg_clv_prob])
    elif table == "by_market":
        writer.writerow(["market", "count", "positive_rate", "avg_clv_line", "avg_clv_prob"])
        rows = report.by_market
        if len(rows) > OUTCOMES_EXPORT_MAX_ROWS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV export row limit exceeded")
        for row in rows:
            writer.writerow([row.name, row.count, row.positive_rate, row.avg_clv_line, row.avg_clv_prob])
    else:
        writer.writerow(["reason", "count"])
        rows = report.top_filtered_reasons
        if len(rows) > OUTCOMES_EXPORT_MAX_ROWS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV export row limit exceeded")
        for row in rows:
            writer.writerow([row.reason, row.count])

    return buffer.getvalue()


@router.get("/overview", response_model=AdminOverviewOut)
async def admin_overview(
    days: int = Query(7, ge=1, le=30),
    cycle_limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> AdminOverviewOut:
    report_payload = await build_operator_report(db, days)
    report = OperatorReport(**report_payload)
    conversion_payload = await get_teaser_conversion_funnel(db, days=days)
    conversion = ConversionFunnelOut(**conversion_payload)

    cutoff = datetime.now(UTC) - timedelta(days=days)
    cycle_stmt = (
        select(CycleKpi)
        .where(CycleKpi.started_at >= cutoff)
        .order_by(CycleKpi.started_at.desc())
        .limit(cycle_limit)
    )
    cycles = (await db.execute(cycle_stmt)).scalars().all()

    return AdminOverviewOut(
        report=report,
        recent_cycles=[CycleKpiOut.model_validate(row) for row in cycles],
        conversion=conversion,
    )


@router.get("/conversion/funnel", response_model=ConversionFunnelOut)
async def admin_conversion_funnel(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> ConversionFunnelOut:
    payload = await get_teaser_conversion_funnel(db, days=days)
    return ConversionFunnelOut(**payload)


@router.get("/outcomes/report", response_model=AdminOutcomesReportOut)
async def admin_outcomes_report(
    days: int = Query(30, ge=7, le=90),
    baseline_days: int = Query(14, ge=7, le=30),
    sport_key: str | None = Query(
        None,
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    signal_type: str | None = Query(None, min_length=1, max_length=64),
    market: str | None = Query(None, min_length=1, max_length=32),
    time_bucket: str | None = Query(None, min_length=3, max_length=16),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminOutcomesReportOut:
    normalized_signal_type = _normalize_optional_filter(signal_type)
    normalized_market = _normalize_optional_filter(market)
    normalized_time_bucket = _normalize_time_bucket_filter(time_bucket)
    report_payload = await build_admin_outcomes_report(
        db,
        days=days,
        baseline_days=baseline_days,
        sport_key=sport_key,
        signal_type=normalized_signal_type,
        market=normalized_market,
        time_bucket=normalized_time_bucket,
    )
    logger.info(
        "admin_outcomes_report_generated",
        extra={
            "days": days,
            "baseline_days": baseline_days,
            "sport_key": sport_key,
            "signal_type": normalized_signal_type,
            "market": normalized_market,
            "time_bucket": normalized_time_bucket,
        },
    )
    return AdminOutcomesReportOut(**report_payload)


@router.get("/outcomes/export.json")
async def admin_outcomes_export_json(
    days: int = Query(30, ge=7, le=90),
    baseline_days: int = Query(14, ge=7, le=30),
    sport_key: str | None = Query(
        None,
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    signal_type: str | None = Query(None, min_length=1, max_length=64),
    market: str | None = Query(None, min_length=1, max_length=32),
    time_bucket: str | None = Query(None, min_length=3, max_length=16),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> Response:
    normalized_signal_type = _normalize_optional_filter(signal_type)
    normalized_market = _normalize_optional_filter(market)
    normalized_time_bucket = _normalize_time_bucket_filter(time_bucket)
    report_payload = await build_admin_outcomes_report(
        db,
        days=days,
        baseline_days=baseline_days,
        sport_key=sport_key,
        signal_type=normalized_signal_type,
        market=normalized_market,
        time_bucket=normalized_time_bucket,
    )
    report = AdminOutcomesReportOut(**report_payload)
    filename = _build_outcomes_filename("report", "json")
    logger.info(
        "admin_outcomes_export_json_generated",
        extra={
            "days": days,
            "baseline_days": baseline_days,
            "sport_key": sport_key,
            "signal_type": normalized_signal_type,
            "market": normalized_market,
            "time_bucket": normalized_time_bucket,
        },
    )
    return Response(
        content=report.model_dump_json(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/outcomes/export.csv")
async def admin_outcomes_export_csv(
    table: Literal["summary", "by_signal_type", "by_market", "top_filtered_reasons"] = Query("summary"),
    days: int = Query(30, ge=7, le=90),
    baseline_days: int = Query(14, ge=7, le=30),
    sport_key: str | None = Query(
        None,
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    signal_type: str | None = Query(None, min_length=1, max_length=64),
    market: str | None = Query(None, min_length=1, max_length=32),
    time_bucket: str | None = Query(None, min_length=3, max_length=16),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    normalized_signal_type = _normalize_optional_filter(signal_type)
    normalized_market = _normalize_optional_filter(market)
    normalized_time_bucket = _normalize_time_bucket_filter(time_bucket)
    report_payload = await build_admin_outcomes_report(
        db,
        days=days,
        baseline_days=baseline_days,
        sport_key=sport_key,
        signal_type=normalized_signal_type,
        market=normalized_market,
        time_bucket=normalized_time_bucket,
    )
    report = AdminOutcomesReportOut(**report_payload)
    csv_content = _render_outcomes_csv(report, table=table)
    filename = _build_outcomes_filename(table, "csv")
    logger.info(
        "admin_outcomes_export_csv_generated",
        extra={
            "table": table,
            "days": days,
            "baseline_days": baseline_days,
            "sport_key": sport_key,
            "signal_type": normalized_signal_type,
            "market": normalized_market,
            "time_bucket": normalized_time_bucket,
        },
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit/logs", response_model=AdminAuditLogListOut)
async def admin_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action_type: str | None = Query(None, min_length=1, max_length=128),
    target_type: str | None = Query(None, min_length=1, max_length=64),
    actor_user_id: UUID | None = None,
    target_id: str | None = Query(None, min_length=1, max_length=64),
    since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminAuditLogListOut:
    filters = []
    if action_type:
        filters.append(AdminAuditLog.action_type == action_type.strip())
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type.strip())
    if actor_user_id is not None:
        filters.append(AdminAuditLog.actor_user_id == actor_user_id)
    if target_id:
        filters.append(AdminAuditLog.target_id == target_id.strip())
    if since is not None:
        filters.append(AdminAuditLog.created_at >= since)

    count_stmt = select(func.count(AdminAuditLog.id))
    data_stmt = select(AdminAuditLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
        data_stmt = data_stmt.where(*filters)
    data_stmt = data_stmt.order_by(AdminAuditLog.created_at.desc()).limit(limit).offset(offset)

    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = list((await db.execute(data_stmt)).scalars().all())
    return AdminAuditLogListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[AdminAuditLogItemOut.model_validate(row) for row in rows],
    )


@router.get("/users", response_model=AdminUserSearchListOut)
async def admin_search_users(
    q: str = Query(..., min_length=2, max_length=128),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminUserSearchListOut:
    query = q.strip()
    if not query:
        return AdminUserSearchListOut(total=0, limit=limit, items=[])

    lowered = query.lower()
    filter_expr = or_(
        func.lower(User.email).like(f"%{lowered}%"),
        User.id.cast(String).like(f"%{query}%"),
    )

    count_stmt = select(func.count(User.id)).where(filter_expr)
    data_stmt = select(User).where(filter_expr).order_by(User.created_at.desc()).limit(limit)

    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = list((await db.execute(data_stmt)).scalars().all())

    return AdminUserSearchListOut(
        total=total,
        limit=limit,
        items=[AdminUserSearchItemOut.model_validate(row) for row in rows],
    )


@router.patch("/users/{user_id}/active", response_model=AdminUserActiveUpdateOut)
async def admin_update_user_active(
    user_id: UUID,
    payload: AdminUserActiveUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_USER_STATUS_WRITE)),
) -> AdminUserActiveUpdateOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_is_active = target_user.is_active
    target_user.is_active = payload.is_active

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.user.active.update",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"is_active": old_is_active},
        after_payload={"is_active": target_user.is_active},
        request_id=request.headers.get("x-request-id"),
    )

    await db.commit()
    await db.refresh(target_user)
    await db.refresh(audit)

    return AdminUserActiveUpdateOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        old_is_active=old_is_active,
        new_is_active=target_user.is_active,
        reason=audit.reason,
    )


@router.post("/users/{user_id}/password-reset", response_model=AdminUserPasswordResetOut)
async def admin_request_user_password_reset(
    user_id: UUID,
    payload: AdminUserPasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_USER_PASSWORD_RESET_WRITE)),
) -> AdminUserPasswordResetOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not target_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user is inactive")

    now = datetime.now(UTC)
    reset_invalidate_result = await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == target_user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    had_active_reset_token = bool((reset_invalidate_result.rowcount or 0) > 0)

    raw_token = generate_password_reset_token()
    reset_token = PasswordResetToken(
        user_id=target_user.id,
        token_hash=hash_password_reset_token(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
    )
    db.add(reset_token)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.user.password_reset.request",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"had_active_reset_token": had_active_reset_token},
        after_payload={"reset_token_issued": True},
        request_id=request.headers.get("x-request-id"),
    )

    await db.commit()
    await db.refresh(audit)

    response = AdminUserPasswordResetOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        message="Password reset requested successfully",
    )
    if settings.app_env != "production":
        response.reset_token = raw_token
        response.expires_in_minutes = settings.password_reset_token_expire_minutes
    return response


def _serialize_subscription_for_audit(subscription: Subscription | None) -> dict | None:
    if subscription is None:
        return None
    return {
        "stripe_subscription_id": subscription.stripe_subscription_id,
        "status": subscription.status,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "current_period_end": subscription.current_period_end.isoformat()
        if subscription.current_period_end is not None
        else None,
    }


def _build_admin_api_partner_entitlement_out(
    target_user: User,
    entitlement: ApiPartnerEntitlement | None,
) -> AdminApiPartnerEntitlementOut:
    if entitlement is None:
        return AdminApiPartnerEntitlementOut(
            entitlement_id=None,
            user_id=target_user.id,
            email=target_user.email,
            plan_code=None,
            api_access_enabled=False,
            soft_limit_monthly=None,
            overage_enabled=True,
            overage_price_cents=None,
            overage_unit_quantity=DEFAULT_OVERAGE_UNIT_QUANTITY,
            created_at=None,
            updated_at=None,
        )
    return AdminApiPartnerEntitlementOut(
        entitlement_id=entitlement.id,
        user_id=target_user.id,
        email=target_user.email,
        plan_code=entitlement.plan_code,
        api_access_enabled=entitlement.api_access_enabled,
        soft_limit_monthly=entitlement.soft_limit_monthly,
        overage_enabled=entitlement.overage_enabled,
        overage_price_cents=entitlement.overage_price_cents,
        overage_unit_quantity=entitlement.overage_unit_quantity,
        created_at=entitlement.created_at,
        updated_at=entitlement.updated_at,
    )


@router.get("/users/{user_id}/billing", response_model=AdminUserBillingOverviewOut)
async def admin_user_billing_overview(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminUserBillingOverviewOut:
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    local_subscription = await get_latest_subscription_for_user(db, target_user.id)
    return AdminUserBillingOverviewOut(
        user_id=target_user.id,
        email=target_user.email,
        tier=target_user.tier,
        is_active=target_user.is_active,
        stripe_customer_id=target_user.stripe_customer_id,
        subscription=AdminBillingSubscriptionOut.model_validate(local_subscription)
        if local_subscription is not None
        else None,
    )


@router.post("/users/{user_id}/billing/resync", response_model=AdminBillingMutationOut)
async def admin_user_billing_resync(
    user_id: UUID,
    payload: AdminBillingMutationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_BILLING_WRITE)),
) -> AdminBillingMutationOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    before_subscription = await get_latest_subscription_for_user(db, target_user.id)
    before_status = before_subscription.status if before_subscription is not None else None
    before_cancel = (
        before_subscription.cancel_at_period_end if before_subscription is not None else None
    )
    before_tier = target_user.tier

    try:
        after_subscription = await admin_resync_user_subscription(db, user=target_user)
    except Exception as exc:
        _raise_billing_error(exc)
    await db.refresh(target_user)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.billing.resync",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={
            "tier": before_tier,
            "subscription": _serialize_subscription_for_audit(before_subscription),
        },
        after_payload={
            "tier": target_user.tier,
            "subscription": _serialize_subscription_for_audit(after_subscription),
        },
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)

    return AdminBillingMutationOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="resync",
        previous_status=before_status,
        new_status=after_subscription.status if after_subscription is not None else None,
        previous_cancel_at_period_end=before_cancel,
        new_cancel_at_period_end=(
            after_subscription.cancel_at_period_end if after_subscription is not None else None
        ),
        subscription_id=(
            after_subscription.stripe_subscription_id if after_subscription is not None else None
        ),
    )


@router.post("/users/{user_id}/billing/cancel", response_model=AdminBillingMutationOut)
async def admin_user_billing_cancel(
    user_id: UUID,
    payload: AdminBillingMutationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_BILLING_WRITE)),
) -> AdminBillingMutationOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    before_subscription = await get_latest_subscription_for_user(db, target_user.id)
    before_status = before_subscription.status if before_subscription is not None else None
    before_cancel = (
        before_subscription.cancel_at_period_end if before_subscription is not None else None
    )

    try:
        after_subscription = await admin_cancel_user_subscription(db, user=target_user)
    except Exception as exc:
        _raise_billing_error(exc)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.billing.cancel",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"subscription": _serialize_subscription_for_audit(before_subscription)},
        after_payload={"subscription": _serialize_subscription_for_audit(after_subscription)},
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)

    return AdminBillingMutationOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="cancel",
        previous_status=before_status,
        new_status=after_subscription.status,
        previous_cancel_at_period_end=before_cancel,
        new_cancel_at_period_end=after_subscription.cancel_at_period_end,
        subscription_id=after_subscription.stripe_subscription_id,
    )


@router.post("/users/{user_id}/billing/reactivate", response_model=AdminBillingMutationOut)
async def admin_user_billing_reactivate(
    user_id: UUID,
    payload: AdminBillingMutationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_BILLING_WRITE)),
) -> AdminBillingMutationOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    before_subscription = await get_latest_subscription_for_user(db, target_user.id)
    before_status = before_subscription.status if before_subscription is not None else None
    before_cancel = (
        before_subscription.cancel_at_period_end if before_subscription is not None else None
    )

    try:
        after_subscription = await admin_reactivate_user_subscription(db, user=target_user)
    except Exception as exc:
        _raise_billing_error(exc)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.billing.reactivate",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"subscription": _serialize_subscription_for_audit(before_subscription)},
        after_payload={"subscription": _serialize_subscription_for_audit(after_subscription)},
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)

    return AdminBillingMutationOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="reactivate",
        previous_status=before_status,
        new_status=after_subscription.status,
        previous_cancel_at_period_end=before_cancel,
        new_cancel_at_period_end=after_subscription.cancel_at_period_end,
        subscription_id=after_subscription.stripe_subscription_id,
    )


@router.get("/users/{user_id}/api-keys", response_model=AdminApiPartnerKeyListOut)
async def admin_list_user_api_partner_keys(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminApiPartnerKeyListOut:
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    keys = await list_api_partner_keys_for_user(db, target_user.id)
    now = datetime.now(UTC)
    recently_used_cutoff = now - timedelta(days=30)
    active_keys = sum(1 for key in keys if key.is_active)
    recently_used = sum(
        1 for key in keys if key.last_used_at is not None and key.last_used_at >= recently_used_cutoff
    )
    return AdminApiPartnerKeyListOut(
        user_id=target_user.id,
        email=target_user.email,
        tier=target_user.tier,
        total_keys=len(keys),
        active_keys=active_keys,
        recently_used_30d=recently_used,
        items=[AdminApiPartnerKeyOut.model_validate(row) for row in keys],
    )


@router.post("/users/{user_id}/api-keys", response_model=AdminApiPartnerKeyIssueOut)
async def admin_issue_user_api_partner_key(
    user_id: UUID,
    payload: AdminApiPartnerKeyIssueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_PARTNER_API_WRITE)),
) -> AdminApiPartnerKeyIssueOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    keys_before = await list_api_partner_keys_for_user(db, target_user.id)
    active_before = sum(1 for row in keys_before if row.is_active)
    key, raw_api_key = await issue_api_partner_key(
        db,
        user_id=target_user.id,
        created_by_user_id=admin_user.id,
        name=payload.name,
        expires_at=_resolve_expires_at(payload.expires_in_days),
    )

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.partner_api_key.issue",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"active_keys": active_before},
        after_payload={
            "active_keys": active_before + 1,
            "key": serialize_api_partner_key_for_audit(key),
        },
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(key)

    return AdminApiPartnerKeyIssueOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="issue",
        key=AdminApiPartnerKeyOut.model_validate(key),
        api_key=raw_api_key,
    )


@router.post("/users/{user_id}/api-keys/{key_id}/revoke", response_model=AdminApiPartnerKeyRevokeOut)
async def admin_revoke_user_api_partner_key(
    user_id: UUID,
    key_id: UUID,
    payload: AdminApiPartnerKeyMutationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_PARTNER_API_WRITE)),
) -> AdminApiPartnerKeyRevokeOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    key = await _get_partner_key_for_user(db, user_id=target_user.id, key_id=key_id)
    old_is_active = key.is_active
    before_payload = serialize_api_partner_key_for_audit(key)
    await revoke_api_partner_key(db, key=key)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.partner_api_key.revoke",
        target_type="api_partner_key",
        target_id=str(key.id),
        reason=payload.reason.strip(),
        before_payload=before_payload,
        after_payload=serialize_api_partner_key_for_audit(key),
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(key)

    return AdminApiPartnerKeyRevokeOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="revoke",
        key_id=key.id,
        key_prefix=key.key_prefix,
        old_is_active=old_is_active,
        new_is_active=key.is_active,
        revoked_at=key.revoked_at,
    )


@router.post("/users/{user_id}/api-keys/{key_id}/rotate", response_model=AdminApiPartnerKeyIssueOut)
async def admin_rotate_user_api_partner_key(
    user_id: UUID,
    key_id: UUID,
    payload: AdminApiPartnerKeyRotateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_PARTNER_API_WRITE)),
) -> AdminApiPartnerKeyIssueOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    key = await _get_partner_key_for_user(db, user_id=target_user.id, key_id=key_id)
    if not key.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active keys can be rotated")

    before_payload = serialize_api_partner_key_for_audit(key)
    rotated_key, raw_api_key = await rotate_api_partner_key(
        db,
        key=key,
        created_by_user_id=admin_user.id,
        name=payload.name,
        expires_at=_resolve_expires_at(payload.expires_in_days),
    )

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.partner_api_key.rotate",
        target_type="api_partner_key",
        target_id=str(key.id),
        reason=payload.reason.strip(),
        before_payload=before_payload,
        after_payload={
            "previous_key_id": str(key.id),
            "new_key": serialize_api_partner_key_for_audit(rotated_key),
        },
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(rotated_key)

    return AdminApiPartnerKeyIssueOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        operation="rotate",
        key=AdminApiPartnerKeyOut.model_validate(rotated_key),
        api_key=raw_api_key,
    )


@router.get("/users/{user_id}/api-entitlement", response_model=AdminApiPartnerEntitlementOut)
async def admin_get_user_api_partner_entitlement(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminApiPartnerEntitlementOut:
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    entitlement = await get_api_partner_entitlement(db, user_id=target_user.id)
    return _build_admin_api_partner_entitlement_out(target_user, entitlement)


@router.patch("/users/{user_id}/api-entitlement", response_model=AdminApiPartnerEntitlementUpdateOut)
async def admin_update_user_api_partner_entitlement(
    user_id: UUID,
    payload: AdminApiPartnerEntitlementUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_PARTNER_API_WRITE)),
) -> AdminApiPartnerEntitlementUpdateOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    entitlement = await get_or_create_api_partner_entitlement(db, user_id=target_user.id)
    old_state = _build_admin_api_partner_entitlement_out(target_user, entitlement)

    if "plan_code" in payload.model_fields_set:
        entitlement.plan_code = payload.plan_code
    if "api_access_enabled" in payload.model_fields_set and payload.api_access_enabled is not None:
        entitlement.api_access_enabled = payload.api_access_enabled
    if "soft_limit_monthly" in payload.model_fields_set:
        entitlement.soft_limit_monthly = payload.soft_limit_monthly
    if "overage_enabled" in payload.model_fields_set and payload.overage_enabled is not None:
        entitlement.overage_enabled = payload.overage_enabled
    if "overage_price_cents" in payload.model_fields_set:
        entitlement.overage_price_cents = payload.overage_price_cents
    if "overage_unit_quantity" in payload.model_fields_set and payload.overage_unit_quantity is not None:
        entitlement.overage_unit_quantity = payload.overage_unit_quantity

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.partner_entitlement.update",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload=old_state.model_dump(mode="json"),
        after_payload=serialize_api_partner_entitlement_for_audit(entitlement),
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(entitlement)
    await db.refresh(audit)

    return AdminApiPartnerEntitlementUpdateOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        reason=audit.reason,
        old_entitlement=old_state,
        new_entitlement=_build_admin_api_partner_entitlement_out(target_user, entitlement),
    )


@router.patch("/users/{user_id}/tier", response_model=AdminUserTierUpdateOut)
async def admin_update_user_tier(
    user_id: UUID,
    payload: AdminUserTierUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_USER_TIER_WRITE)),
) -> AdminUserTierUpdateOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_tier = target_user.tier
    target_user.tier = payload.tier

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.user.tier.update",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"tier": old_tier},
        after_payload={"tier": target_user.tier},
        request_id=request.headers.get("x-request-id"),
    )

    await db.commit()
    await db.refresh(target_user)
    await db.refresh(audit)

    return AdminUserTierUpdateOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        old_tier=old_tier,
        new_tier=target_user.tier,
        reason=audit.reason,
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserRoleUpdateOut)
async def admin_update_user_role(
    user_id: UUID,
    payload: AdminUserRoleUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_USER_ROLE_WRITE)),
) -> AdminUserRoleUpdateOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_admin_role = target_user.admin_role
    old_is_admin = target_user.is_admin

    target_user.admin_role = payload.admin_role
    target_user.is_admin = payload.admin_role is not None

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.user.role.update",
        target_type="user",
        target_id=str(target_user.id),
        reason=payload.reason.strip(),
        before_payload={"admin_role": old_admin_role, "is_admin": old_is_admin},
        after_payload={"admin_role": target_user.admin_role, "is_admin": target_user.is_admin},
        request_id=request.headers.get("x-request-id"),
    )

    await db.commit()
    await db.refresh(target_user)
    await db.refresh(audit)

    return AdminUserRoleUpdateOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        user_id=target_user.id,
        email=target_user.email,
        old_admin_role=old_admin_role,
        new_admin_role=target_user.admin_role,
        old_is_admin=old_is_admin,
        new_is_admin=target_user.is_admin,
        reason=audit.reason,
    )


# ── Cross-market divergence export ──────────────────────────────────


_DIVERGENCE_CSV_COLUMNS = [
    "created_at",
    "canonical_event_key",
    "divergence_type",
    "lead_source",
    "sportsbook_threshold_value",
    "exchange_probability_threshold",
    "sportsbook_break_timestamp",
    "exchange_break_timestamp",
    "lag_seconds",
    "resolved",
    "resolved_at",
    "resolution_type",
    "idempotency_key",
]


@router.get("/divergence/list")
async def admin_divergence_list(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    divergence_type: str | None = Query(None, min_length=3, max_length=30),
    canonical_event_key: str | None = Query(None, min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> dict:
    filters: list = []
    if divergence_type:
        filters.append(CrossMarketDivergenceEvent.divergence_type == divergence_type.strip().upper())
    if canonical_event_key:
        filters.append(CrossMarketDivergenceEvent.canonical_event_key == canonical_event_key.strip())

    count_stmt = select(func.count(CrossMarketDivergenceEvent.id))
    data_stmt = select(CrossMarketDivergenceEvent)
    if filters:
        count_stmt = count_stmt.where(*filters)
        data_stmt = data_stmt.where(*filters)
    data_stmt = data_stmt.order_by(CrossMarketDivergenceEvent.created_at.desc()).limit(limit).offset(offset)

    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = list((await db.execute(data_stmt)).scalars().all())

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {col: _serialize_divergence_field(getattr(row, col)) for col in _DIVERGENCE_CSV_COLUMNS}
            for row in rows
        ],
    }


@router.get("/divergence/export.csv")
async def admin_divergence_export_csv(
    days: int = Query(7, ge=1, le=90),
    divergence_type: str | None = Query(None, min_length=3, max_length=30),
    canonical_event_key: str | None = Query(None, min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    filters = [CrossMarketDivergenceEvent.created_at >= cutoff]
    if divergence_type:
        filters.append(CrossMarketDivergenceEvent.divergence_type == divergence_type.strip().upper())
    if canonical_event_key:
        filters.append(CrossMarketDivergenceEvent.canonical_event_key == canonical_event_key.strip())

    stmt = (
        select(CrossMarketDivergenceEvent)
        .where(*filters)
        .order_by(CrossMarketDivergenceEvent.created_at.desc())
        .limit(DIVERGENCE_EXPORT_MAX_ROWS)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_DIVERGENCE_CSV_COLUMNS)
    for row in rows:
        writer.writerow([_serialize_divergence_field(getattr(row, col)) for col in _DIVERGENCE_CSV_COLUMNS])

    csv_content = buffer.getvalue()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"admin-divergence-export-{timestamp}.csv"

    logger.info(
        "admin_divergence_export_csv_generated",
        extra={"days": days, "rows": len(rows), "divergence_type": divergence_type},
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _serialize_divergence_field(value: object) -> str:
    """Serialize a single field value for CSV/JSON output."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ── API usage metering endpoints ──────────────────────────────────


@router.get("/users/{user_id}/api-usage")
async def admin_user_api_usage(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> dict:
    """Current period usage, limit, remaining, and overage for a partner."""
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    from app.services.api_usage_tracking import get_usage_and_limits

    usage = await get_usage_and_limits(redis, db, str(target_user.id))
    return {"user_id": str(target_user.id), "email": target_user.email, **usage}


@router.get("/users/{user_id}/api-usage/history")
async def admin_user_api_usage_history(
    user_id: UUID,
    limit: int = Query(12, ge=1, le=60),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> dict:
    """Historical usage periods for a partner."""
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    from app.services.api_usage_tracking import get_usage_history

    periods = await get_usage_history(db, str(target_user.id), limit=limit, offset=offset)
    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "request_count": p.request_count,
                "included_limit": p.included_limit,
                "overage_count": p.overage_count,
                "stripe_meter_synced_at": p.stripe_meter_synced_at.isoformat() if p.stripe_meter_synced_at else None,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in periods
        ],
    }


@router.get("/users/{user_id}/api-keys/{key_id}/usage")
async def admin_key_api_usage(
    user_id: UUID,
    key_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> dict:
    """Current period usage for a specific API partner key."""
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    key = await _get_partner_key_for_user(db, user_id=target_user.id, key_id=key_id)

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    from app.services.api_usage_tracking import get_key_current_usage, get_usage_and_limits

    key_count = await get_key_current_usage(redis, str(target_user.id), str(key.id))
    user_usage = await get_usage_and_limits(redis, db, str(target_user.id))

    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "key_id": str(key.id),
        "key_name": key.name,
        "key_prefix": key.key_prefix,
        "is_active": key.is_active,
        "key_request_count": key_count,
        "period_start": user_usage["period_start"],
        "period_end": user_usage["period_end"],
        "included_limit": user_usage["included_limit"],
        "user_request_count": user_usage["request_count"],
        "is_over_limit": user_usage["is_over_limit"],
        "overage_count": user_usage["overage_count"],
    }


@router.get("/users/{user_id}/api-keys/{key_id}/usage/history")
async def admin_key_api_usage_history(
    user_id: UUID,
    key_id: UUID,
    limit: int = Query(12, ge=1, le=60),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> dict:
    """Historical usage periods for a specific API partner key."""
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await _get_partner_key_for_user(db, user_id=target_user.id, key_id=key_id)

    from app.services.api_usage_tracking import get_key_usage_history

    periods = await get_key_usage_history(
        db, str(target_user.id), str(key_id), limit=limit, offset=offset
    )
    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "key_id": str(key_id),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "request_count": p.request_count,
                "included_limit": p.included_limit,
                "overage_count": p.overage_count,
                "stripe_meter_synced_at": p.stripe_meter_synced_at.isoformat() if p.stripe_meter_synced_at else None,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in periods
        ],
    }


# ── Ops service token management ────────────────────────────────────


@router.get("/ops-tokens", response_model=AdminOpsServiceTokenListOut)
async def admin_list_ops_service_tokens(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminOpsServiceTokenListOut:
    tokens = await list_ops_service_tokens(db)
    active = sum(1 for t in tokens if t.is_active)
    return AdminOpsServiceTokenListOut(
        total=len(tokens),
        active=active,
        items=[AdminOpsServiceTokenOut.model_validate(t) for t in tokens],
    )


@router.get("/ops-tokens/{token_id}", response_model=AdminOpsServiceTokenOut)
async def admin_get_ops_service_token(
    token_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> AdminOpsServiceTokenOut:
    token = await get_ops_service_token(db, token_id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ops service token not found")
    return AdminOpsServiceTokenOut.model_validate(token)


@router.post("/ops-tokens", response_model=AdminOpsServiceTokenIssueOut)
async def admin_issue_ops_service_token(
    payload: AdminOpsServiceTokenIssueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_OPS_TOKEN_WRITE)),
) -> AdminOpsServiceTokenIssueOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    try:
        token, raw_key = await issue_ops_service_token(
            db,
            created_by_user_id=admin_user.id,
            name=payload.name,
            scopes=payload.scopes,
            expires_at=_resolve_expires_at(payload.expires_in_days),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.ops_token.issue",
        target_type="ops_service_token",
        target_id=str(token.id),
        reason=payload.reason.strip(),
        before_payload={},
        after_payload=serialize_ops_service_token_for_audit(token),
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(token)

    return AdminOpsServiceTokenIssueOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        reason=audit.reason,
        operation="issue",
        token=AdminOpsServiceTokenOut.model_validate(token),
        raw_key=raw_key,
    )


@router.post("/ops-tokens/{token_id}/revoke", response_model=AdminOpsServiceTokenRevokeOut)
async def admin_revoke_ops_service_token(
    token_id: UUID,
    payload: AdminOpsServiceTokenMutationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_OPS_TOKEN_WRITE)),
) -> AdminOpsServiceTokenRevokeOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    token = await get_ops_service_token(db, token_id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ops service token not found")

    old_is_active = token.is_active
    before_payload = serialize_ops_service_token_for_audit(token)
    await revoke_ops_service_token(db, token=token)

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.ops_token.revoke",
        target_type="ops_service_token",
        target_id=str(token.id),
        reason=payload.reason.strip(),
        before_payload=before_payload,
        after_payload=serialize_ops_service_token_for_audit(token),
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(token)

    return AdminOpsServiceTokenRevokeOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        reason=audit.reason,
        operation="revoke",
        token_id=token.id,
        key_prefix=token.key_prefix,
        old_is_active=old_is_active,
        new_is_active=token.is_active,
        revoked_at=token.revoked_at,
    )


@router.post("/ops-tokens/{token_id}/rotate", response_model=AdminOpsServiceTokenIssueOut)
async def admin_rotate_ops_service_token(
    token_id: UUID,
    payload: AdminOpsServiceTokenRotateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_OPS_TOKEN_WRITE)),
) -> AdminOpsServiceTokenIssueOut:
    _require_step_up_auth(
        admin_user,
        step_up_password=payload.step_up_password,
        confirm_phrase=payload.confirm_phrase,
        mfa_code=payload.mfa_code,
    )

    token = await get_ops_service_token(db, token_id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ops service token not found")
    if not token.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active tokens can be rotated")

    before_payload = serialize_ops_service_token_for_audit(token)
    try:
        rotated_token, raw_key = await rotate_ops_service_token(
            db,
            token=token,
            created_by_user_id=admin_user.id,
            name=payload.name,
            scopes=payload.scopes,
            expires_at=_resolve_expires_at(payload.expires_in_days),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit = await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.ops_token.rotate",
        target_type="ops_service_token",
        target_id=str(token.id),
        reason=payload.reason.strip(),
        before_payload=before_payload,
        after_payload={
            "previous_token_id": str(token.id),
            "new_token": serialize_ops_service_token_for_audit(rotated_token),
        },
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()
    await db.refresh(audit)
    await db.refresh(rotated_token)

    return AdminOpsServiceTokenIssueOut(
        action_id=audit.id,
        acted_at=audit.created_at,
        actor_user_id=admin_user.id,
        reason=audit.reason,
        operation="rotate",
        token=AdminOpsServiceTokenOut.model_validate(rotated_token),
        raw_key=raw_key,
    )
