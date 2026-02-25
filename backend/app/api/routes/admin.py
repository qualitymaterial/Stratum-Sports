from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import String, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_permission, require_admin_user
from app.core.admin_roles import (
    PERMISSION_BILLING_WRITE,
    PERMISSION_ADMIN_READ,
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
from app.models.cycle_kpi import CycleKpi
from app.models.password_reset_token import PasswordResetToken
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.ops import (
    AdminBillingMutationOut,
    AdminBillingMutationRequest,
    AdminBillingSubscriptionOut,
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
from app.services.operator_report import build_operator_report
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


def _require_step_up_auth(admin_user: User, step_up_password: str, confirm_phrase: str) -> None:
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


def _raise_billing_error(exc: Exception) -> None:
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Billing operation failed: {exc}") from exc


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
