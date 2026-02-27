from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OpsTokenIdentity, require_ops_scope
from app.core.database import get_db
from app.models.cycle_kpi import CycleKpi
from app.schemas.ops import CycleKpiOut, CycleSummaryOut, OperatorReport, SignalTypeCount
from app.services.operator_report import build_operator_report

router = APIRouter()


@router.get("/cycles", response_model=list[CycleKpiOut])
async def list_cycles(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _ops: OpsTokenIdentity = Depends(require_ops_scope("ops:read")),
) -> list[CycleKpiOut]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(CycleKpi)
        .where(CycleKpi.started_at >= cutoff)
        .order_by(CycleKpi.started_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [CycleKpiOut.model_validate(row) for row in rows]


@router.get("/cycles/summary", response_model=CycleSummaryOut)
async def cycles_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _ops: OpsTokenIdentity = Depends(require_ops_scope("ops:read")),
) -> CycleSummaryOut:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    agg_stmt = select(
        func.count(CycleKpi.id).label("total_cycles"),
        func.avg(CycleKpi.duration_ms).label("avg_duration_ms"),
        func.coalesce(func.sum(CycleKpi.snapshots_inserted), 0).label("total_snapshots_inserted"),
        func.coalesce(func.sum(CycleKpi.signals_created_total), 0).label("total_signals_created"),
        func.coalesce(func.sum(CycleKpi.alerts_sent), 0).label("alerts_sent"),
        func.coalesce(func.sum(CycleKpi.alerts_failed), 0).label("alerts_failed"),
        func.coalesce(func.sum(CycleKpi.requests_used_delta), 0).label("requests_used_delta"),
    ).where(CycleKpi.started_at >= cutoff)
    agg = (await db.execute(agg_stmt)).mappings().one()

    type_stmt = select(CycleKpi.signals_created_by_type).where(CycleKpi.started_at >= cutoff)
    type_rows = (await db.execute(type_stmt)).all()
    counts: Counter[str] = Counter()
    for row in type_rows:
        payload = row[0]
        if not isinstance(payload, dict):
            continue
        for raw_signal_type, raw_count in payload.items():
            signal_type = str(raw_signal_type).strip()
            if not signal_type:
                continue
            try:
                parsed = int(raw_count)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                counts[signal_type] += parsed

    top_signal_types = [
        SignalTypeCount(signal_type=signal_type, count=count)
        for signal_type, count in counts.most_common()
    ]

    avg_duration = agg["avg_duration_ms"]
    return CycleSummaryOut(
        total_cycles=int(agg["total_cycles"] or 0),
        avg_duration_ms=float(avg_duration) if avg_duration is not None else None,
        total_snapshots_inserted=int(agg["total_snapshots_inserted"] or 0),
        total_signals_created=int(agg["total_signals_created"] or 0),
        alerts_sent=int(agg["alerts_sent"] or 0),
        alerts_failed=int(agg["alerts_failed"] or 0),
        requests_used_delta=int(agg["requests_used_delta"] or 0),
        top_signal_types=top_signal_types,
    )


@router.get("/report", response_model=OperatorReport)
async def operator_report(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    _ops: OpsTokenIdentity = Depends(require_ops_scope("ops:read")),
) -> OperatorReport:
    report = await build_operator_report(db, days)
    return OperatorReport(**report)
