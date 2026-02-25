from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_permission, require_admin_user
from app.core.admin_roles import PERMISSION_USER_TIER_WRITE
from app.core.database import get_db
from app.models.cycle_kpi import CycleKpi
from app.models.user import User
from app.schemas.ops import (
    AdminOverviewOut,
    AdminUserTierUpdateOut,
    AdminUserTierUpdateRequest,
    ConversionFunnelOut,
    CycleKpiOut,
    OperatorReport,
)
from app.services.admin_audit import write_admin_audit_log
from app.services.operator_report import build_operator_report
from app.services.teaser_analytics import get_teaser_conversion_funnel

router = APIRouter()


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


@router.patch("/users/{user_id}/tier", response_model=AdminUserTierUpdateOut)
async def admin_update_user_tier(
    user_id: UUID,
    payload: AdminUserTierUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_permission(PERMISSION_USER_TIER_WRITE)),
) -> AdminUserTierUpdateOut:
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
