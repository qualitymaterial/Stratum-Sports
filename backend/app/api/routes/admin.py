from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_user
from app.core.database import get_db
from app.models.cycle_kpi import CycleKpi
from app.models.user import User
from app.schemas.ops import AdminOverviewOut, ConversionFunnelOut, CycleKpiOut, OperatorReport
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
