from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clv_record import ClvRecord
from app.models.cycle_kpi import CycleKpi
from app.models.game import Game
from app.models.signal import Signal
from app.services.performance_intel import get_signal_lifecycle_summary

OUTCOMES_STATUS_BASELINE_MIN_SAMPLES = 30
OUTCOMES_IMPROVEMENT_THRESHOLD = 0.02
OUTCOMES_ALERT_FAILURE_WORSE_THRESHOLD = 0.01
OUTCOMES_DEGRADED_RATE_WORSE_THRESHOLD = 0.02


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def _normalize_time_bucket(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _apply_time_bucket_filter(stmt: Any, time_bucket: str | None) -> Any:
    if not time_bucket:
        return stmt
    if time_bucket == "UNKNOWN":
        return stmt.where(or_(Signal.time_bucket == "UNKNOWN", Signal.time_bucket.is_(None)))
    return stmt.where(Signal.time_bucket == time_bucket)


async def _compute_clv_kpis(
    db: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
    sport_key: str | None,
    signal_type: str | None,
    market: str | None,
    time_bucket: str | None,
) -> dict[str, Any]:
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1), else_=0)
    stmt = select(
        func.count(ClvRecord.id).label("clv_samples"),
        func.coalesce(func.sum(positive_expr), 0).label("positive_count"),
        func.avg(ClvRecord.clv_line).label("avg_clv_line"),
        func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
    ).where(
        ClvRecord.computed_at >= period_start,
        ClvRecord.computed_at < period_end,
    )

    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)
    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if time_bucket:
        stmt = stmt.join(Signal, Signal.id == ClvRecord.signal_id)
        stmt = _apply_time_bucket_filter(stmt, time_bucket)

    row = (await db.execute(stmt)).mappings().one()
    clv_samples = int(row["clv_samples"] or 0)
    positive_count = int(row["positive_count"] or 0)
    avg_clv_line = _coerce_float(row["avg_clv_line"])
    avg_clv_prob = _coerce_float(row["avg_clv_prob"])
    negative_count = max(0, clv_samples - positive_count)
    clv_positive_rate = _compute_rate(positive_count, clv_samples)

    return {
        "clv_samples": clv_samples,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "clv_positive_rate": clv_positive_rate,
        "avg_clv_line": avg_clv_line,
        "avg_clv_prob": avg_clv_prob,
    }


async def _compute_cycle_reliability_kpis(
    db: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, float]:
    degraded_expr = case((CycleKpi.degraded.is_(True), 1), else_=0)
    stmt = select(
        func.count(CycleKpi.id).label("cycles"),
        func.coalesce(func.sum(degraded_expr), 0).label("degraded_cycles"),
        func.coalesce(func.sum(CycleKpi.alerts_sent), 0).label("alerts_sent"),
        func.coalesce(func.sum(CycleKpi.alerts_failed), 0).label("alerts_failed"),
    ).where(
        CycleKpi.started_at >= period_start,
        CycleKpi.started_at < period_end,
    )
    row = (await db.execute(stmt)).mappings().one()
    cycles = float(row["cycles"] or 0)
    degraded_cycles = float(row["degraded_cycles"] or 0)
    alerts_sent = float(row["alerts_sent"] or 0)
    alerts_failed = float(row["alerts_failed"] or 0)
    alert_attempts = alerts_sent + alerts_failed

    return {
        "degraded_cycle_rate": _compute_rate(degraded_cycles, cycles),
        "alert_failure_rate": _compute_rate(alerts_failed, alert_attempts),
    }


async def _compute_lifecycle_kpis(
    db: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
    sport_key: str | None,
    signal_type: str | None,
    market: str | None,
    time_bucket: str | None,
) -> dict[str, Any]:
    lifecycle = await get_signal_lifecycle_summary(
        db,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=time_bucket,
        created_after=period_start,
        created_before=period_end,
        days=max(1, int((period_end - period_start).days) or 1),
        apply_alert_rules=True,
        connection=None,
    )
    total_detected = float(lifecycle.get("total_detected") or 0)
    sent_signals = float(lifecycle.get("sent_signals") or 0)
    stale_signals = float(lifecycle.get("stale_signals") or 0)
    return {
        "sent_rate": _compute_rate(sent_signals, total_detected),
        "stale_rate": _compute_rate(stale_signals, total_detected),
        "top_filtered_reasons": lifecycle.get("top_filtered_reasons") or [],
    }


async def _build_kpi_set(
    db: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
    sport_key: str | None,
    signal_type: str | None,
    market: str | None,
    time_bucket: str | None,
) -> dict[str, Any]:
    clv_kpis = await _compute_clv_kpis(
        db,
        period_start=period_start,
        period_end=period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=time_bucket,
    )
    lifecycle_kpis = await _compute_lifecycle_kpis(
        db,
        period_start=period_start,
        period_end=period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=time_bucket,
    )
    reliability_kpis = await _compute_cycle_reliability_kpis(
        db,
        period_start=period_start,
        period_end=period_end,
    )
    return {
        **clv_kpis,
        "sent_rate": float(lifecycle_kpis["sent_rate"]),
        "stale_rate": float(lifecycle_kpis["stale_rate"]),
        "degraded_cycle_rate": float(reliability_kpis["degraded_cycle_rate"]),
        "alert_failure_rate": float(reliability_kpis["alert_failure_rate"]),
        "top_filtered_reasons": lifecycle_kpis.get("top_filtered_reasons", []),
    }


async def _build_clv_breakdown(
    db: AsyncSession,
    *,
    dimension: str,
    period_start: datetime,
    period_end: datetime,
    sport_key: str | None,
    signal_type: str | None,
    market: str | None,
    time_bucket: str | None,
) -> list[dict[str, Any]]:
    if dimension == "signal_type":
        group_column = ClvRecord.signal_type
    elif dimension == "market":
        group_column = ClvRecord.market
    else:
        raise ValueError(f"Unsupported breakdown dimension: {dimension}")

    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)
    stmt = (
        select(
            group_column.label("name"),
            func.count(ClvRecord.id).label("count"),
            func.avg(positive_expr).label("positive_rate"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .where(
            ClvRecord.computed_at >= period_start,
            ClvRecord.computed_at < period_end,
        )
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)
    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if time_bucket:
        stmt = stmt.join(Signal, Signal.id == ClvRecord.signal_id)
        stmt = _apply_time_bucket_filter(stmt, time_bucket)

    stmt = stmt.group_by(group_column).order_by(
        func.count(ClvRecord.id).desc(),
        group_column.asc(),
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [
        {
            "name": str(row["name"]),
            "count": int(row["count"] or 0),
            "positive_rate": float(row["positive_rate"] or 0.0),
            "avg_clv_line": _coerce_float(row["avg_clv_line"]),
            "avg_clv_prob": _coerce_float(row["avg_clv_prob"]),
        }
        for row in rows
    ]


def _compute_kpi_delta(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "clv_samples_delta": int(current["clv_samples"]) - int(baseline["clv_samples"]),
        "positive_count_delta": int(current["positive_count"]) - int(baseline["positive_count"]),
        "negative_count_delta": int(current["negative_count"]) - int(baseline["negative_count"]),
        "clv_positive_rate_delta": float(current["clv_positive_rate"]) - float(baseline["clv_positive_rate"]),
        "avg_clv_line_delta": (
            None
            if current["avg_clv_line"] is None or baseline["avg_clv_line"] is None
            else float(current["avg_clv_line"]) - float(baseline["avg_clv_line"])
        ),
        "avg_clv_prob_delta": (
            None
            if current["avg_clv_prob"] is None or baseline["avg_clv_prob"] is None
            else float(current["avg_clv_prob"]) - float(baseline["avg_clv_prob"])
        ),
        "sent_rate_delta": float(current["sent_rate"]) - float(baseline["sent_rate"]),
        "stale_rate_delta": float(current["stale_rate"]) - float(baseline["stale_rate"]),
        "degraded_cycle_rate_delta": float(current["degraded_cycle_rate"])
        - float(baseline["degraded_cycle_rate"]),
        "alert_failure_rate_delta": float(current["alert_failure_rate"])
        - float(baseline["alert_failure_rate"]),
    }


def _derive_status(
    *,
    current_kpis: dict[str, Any],
    baseline_kpis: dict[str, Any],
) -> tuple[str, str]:
    if (
        int(current_kpis["clv_samples"]) < OUTCOMES_STATUS_BASELINE_MIN_SAMPLES
        or int(baseline_kpis["clv_samples"]) < OUTCOMES_STATUS_BASELINE_MIN_SAMPLES
    ):
        return (
            "baseline_building",
            "Collecting CLV samples; status stabilizes after both windows reach 30+ samples.",
        )

    clv_rate_delta = float(current_kpis["clv_positive_rate"]) - float(baseline_kpis["clv_positive_rate"])
    alert_failure_worse = (
        float(current_kpis["alert_failure_rate"])
        > float(baseline_kpis["alert_failure_rate"]) + OUTCOMES_ALERT_FAILURE_WORSE_THRESHOLD
    )
    degraded_rate_worse = (
        float(current_kpis["degraded_cycle_rate"])
        > float(baseline_kpis["degraded_cycle_rate"]) + OUTCOMES_DEGRADED_RATE_WORSE_THRESHOLD
    )
    reliability_worse = alert_failure_worse or degraded_rate_worse

    if clv_rate_delta >= OUTCOMES_IMPROVEMENT_THRESHOLD and not reliability_worse:
        return (
            "improving",
            "CLV positive share improved versus baseline while reliability held steady.",
        )
    if clv_rate_delta <= -OUTCOMES_IMPROVEMENT_THRESHOLD or reliability_worse:
        return (
            "declining",
            "CLV share or reliability regressed versus baseline; investigate signal quality and operations.",
        )
    return ("flat", "KPIs are near baseline with no material reliability drift.")


async def build_admin_outcomes_report(
    db: AsyncSession,
    *,
    days: int = 30,
    baseline_days: int = 14,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    time_bucket: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    period_end = now
    period_start = period_end - timedelta(days=max(1, int(days)))
    baseline_period_end = period_start
    baseline_period_start = baseline_period_end - timedelta(days=max(1, int(baseline_days)))
    normalized_time_bucket = _normalize_time_bucket(time_bucket)

    current_kpis = await _build_kpi_set(
        db,
        period_start=period_start,
        period_end=period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=normalized_time_bucket,
    )
    baseline_kpis = await _build_kpi_set(
        db,
        period_start=baseline_period_start,
        period_end=baseline_period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=normalized_time_bucket,
    )
    by_signal_type = await _build_clv_breakdown(
        db,
        dimension="signal_type",
        period_start=period_start,
        period_end=period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=normalized_time_bucket,
    )
    by_market = await _build_clv_breakdown(
        db,
        dimension="market",
        period_start=period_start,
        period_end=period_end,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        time_bucket=normalized_time_bucket,
    )
    delta_vs_baseline = _compute_kpi_delta(current_kpis, baseline_kpis)
    status, status_reason = _derive_status(current_kpis=current_kpis, baseline_kpis=baseline_kpis)

    return {
        "period_start": period_start,
        "period_end": period_end,
        "baseline_period_start": baseline_period_start,
        "baseline_period_end": baseline_period_end,
        "kpis": {key: value for key, value in current_kpis.items() if key != "top_filtered_reasons"},
        "baseline_kpis": {key: value for key, value in baseline_kpis.items() if key != "top_filtered_reasons"},
        "delta_vs_baseline": delta_vs_baseline,
        "status": status,
        "status_reason": status_reason,
        "by_signal_type": by_signal_type,
        "by_market": by_market,
        "top_filtered_reasons": current_kpis.get("top_filtered_reasons", []),
    }
