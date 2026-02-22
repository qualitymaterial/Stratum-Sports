from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clv_record import ClvRecord
from app.models.cycle_kpi import CycleKpi


async def build_operator_report(db: AsyncSession, days: int) -> dict:
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    degraded_expr = case((CycleKpi.degraded.is_(True), 1), else_=0)
    cycle_agg_stmt = select(
        func.count(CycleKpi.id).label("total_cycles"),
        func.avg(CycleKpi.duration_ms).label("avg_cycle_duration_ms"),
        func.coalesce(func.sum(degraded_expr), 0).label("degraded_cycles"),
        func.coalesce(func.sum(CycleKpi.requests_used_delta), 0).label("total_requests_used"),
        func.avg(CycleKpi.requests_remaining).label("avg_requests_remaining"),
        func.coalesce(func.sum(CycleKpi.snapshots_inserted), 0).label("total_snapshots_inserted"),
        func.coalesce(func.sum(CycleKpi.consensus_points_written), 0).label("total_consensus_points_written"),
        func.coalesce(func.sum(CycleKpi.signals_created_total), 0).label("total_signals_created"),
        func.coalesce(func.sum(CycleKpi.alerts_sent), 0).label("alerts_sent"),
        func.coalesce(func.sum(CycleKpi.alerts_failed), 0).label("alerts_failed"),
    ).where(CycleKpi.started_at >= period_start)
    cycle_agg = (await db.execute(cycle_agg_stmt)).mappings().one()

    signal_distribution_stmt = text(
        """
        SELECT
            j.key AS signal_type,
            SUM(
                CASE
                    WHEN j.value ~ '^-?[0-9]+$' THEN (j.value)::int
                    ELSE 0
                END
            ) AS count
        FROM cycle_kpis ck
        CROSS JOIN LATERAL jsonb_each_text(
            CASE
                WHEN jsonb_typeof(ck.signals_created_by_type) = 'object' THEN ck.signals_created_by_type
                ELSE '{}'::jsonb
            END
        ) AS j(key, value)
        WHERE ck.started_at >= :period_start
        GROUP BY j.key
        HAVING SUM(
            CASE
                WHEN j.value ~ '^-?[0-9]+$' THEN (j.value)::int
                ELSE 0
            END
        ) > 0
        ORDER BY count DESC, j.key ASC
        """
    )
    signal_distribution_rows = (
        await db.execute(signal_distribution_stmt, {"period_start": period_start})
    ).mappings().all()
    signals_created_by_type = {
        str(row["signal_type"]): int(row["count"] or 0)
        for row in signal_distribution_rows
    }

    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)
    clv_by_signal_stmt = (
        select(
            ClvRecord.signal_type.label("signal_type"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .where(ClvRecord.computed_at >= period_start)
        .group_by(ClvRecord.signal_type)
        .order_by(ClvRecord.signal_type.asc())
    )
    clv_by_signal_rows = (await db.execute(clv_by_signal_stmt)).mappings().all()
    clv_by_signal_type = [
        {
            "signal_type": str(row["signal_type"]),
            "count": int(row["count"] or 0),
            "pct_positive": float(row["pct_positive"] or 0.0),
            "avg_clv_line": float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None,
            "avg_clv_prob": float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None,
        }
        for row in clv_by_signal_rows
    ]

    clv_by_market_stmt = (
        select(
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .where(ClvRecord.computed_at >= period_start)
        .group_by(ClvRecord.market)
        .order_by(ClvRecord.market.asc())
    )
    clv_by_market_rows = (await db.execute(clv_by_market_stmt)).mappings().all()
    clv_by_market = [
        {
            "market": str(row["market"]),
            "count": int(row["count"] or 0),
            "pct_positive": float(row["pct_positive"] or 0.0),
            "avg_clv_line": float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None,
            "avg_clv_prob": float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None,
        }
        for row in clv_by_market_rows
    ]

    alerts_sent = int(cycle_agg["alerts_sent"] or 0)
    alerts_failed = int(cycle_agg["alerts_failed"] or 0)
    attempts = alerts_sent + alerts_failed
    alert_failure_rate = float(alerts_failed / attempts) if attempts > 0 else 0.0

    avg_cycle_duration = cycle_agg["avg_cycle_duration_ms"]
    avg_requests_remaining = cycle_agg["avg_requests_remaining"]
    return {
        "days": int(days),
        "period_start": period_start,
        "period_end": period_end,
        "ops": {
            "total_cycles": int(cycle_agg["total_cycles"] or 0),
            "avg_cycle_duration_ms": float(avg_cycle_duration) if avg_cycle_duration is not None else None,
            "degraded_cycles": int(cycle_agg["degraded_cycles"] or 0),
            "total_requests_used": int(cycle_agg["total_requests_used"] or 0),
            "avg_requests_remaining": (
                float(avg_requests_remaining) if avg_requests_remaining is not None else None
            ),
            "total_snapshots_inserted": int(cycle_agg["total_snapshots_inserted"] or 0),
            "total_consensus_points_written": int(cycle_agg["total_consensus_points_written"] or 0),
            "total_signals_created": int(cycle_agg["total_signals_created"] or 0),
            "signals_created_by_type": signals_created_by_type,
        },
        "performance": {
            "clv_by_signal_type": clv_by_signal_type,
            "clv_by_market": clv_by_market,
        },
        "reliability": {
            "alerts_sent": alerts_sent,
            "alerts_failed": alerts_failed,
            "alert_failure_rate": alert_failure_rate,
        },
    }
