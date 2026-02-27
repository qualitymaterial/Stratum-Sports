import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import median, pstdev
from typing import Any
from uuid import UUID

from sqlalchemy import Float, case, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.clv_record import ClvRecord
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.alert_rules import evaluate_signal_for_connection
from app.services.context_score import build_context_score
from app.services.public_signal_surface import (
    apply_structural_core_query_filters,
    is_structural_core_visible,
    signal_display_type,
)
from app.services.signals import american_to_implied_prob
from app.services.time_bucket import compute_time_bucket

logger = logging.getLogger(__name__)
settings = get_settings()


def _normalize_limit(value: int | None, *, default: int = 100) -> int:
    max_limit = max(1, int(settings.performance_max_limit))
    if value is None:
        return min(default, max_limit)
    return max(1, min(int(value), max_limit))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_signal_alert_decision(
    signal: Signal,
    *,
    connection: DiscordConnection | None,
    apply_alert_rules: bool,
) -> tuple[str, str]:
    if not apply_alert_rules:
        return "sent", "Sent: alert rule evaluation disabled."
    if connection is None:
        return "sent", "Sent: no Discord alert rules configured."

    allowed, reason, _thresholds = evaluate_signal_for_connection(
        connection,
        signal,
        steam_discord_enabled=settings.steam_discord_enabled,
    )
    return ("sent", reason) if allowed else ("hidden", reason)


def _signal_freshness(signal: Signal) -> tuple[int, str, int]:
    created_at = _as_utc_datetime(signal.created_at)
    freshness_seconds = max(0, int((datetime.now(UTC) - created_at).total_seconds()))
    stale_threshold = max(180, int(settings.odds_poll_interval_seconds) * 3)
    freshness_bucket = _freshness_bucket(freshness_seconds, stale_threshold)
    return freshness_seconds, freshness_bucket, stale_threshold


def _resolve_signal_lifecycle(
    *,
    alert_decision: str,
    alert_reason: str,
    freshness_bucket: str,
    freshness_seconds: int,
    apply_alert_rules: bool,
) -> tuple[str, str]:
    if alert_decision == "hidden":
        return "filtered", alert_reason

    if freshness_bucket == "stale":
        freshness_minutes = max(0, freshness_seconds // 60)
        return "stale", f"Signal aged to stale freshness ({freshness_minutes}m old)."

    if alert_decision == "sent":
        return "sent", alert_reason

    if apply_alert_rules:
        return "eligible", "Eligible under alert rules."
    return "eligible", "Eligible: alert rule evaluation disabled."


def _as_utc_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Expected datetime value")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _derive_consensus_from_quotes(
    market: str,
    quotes: list[OddsSnapshot],
) -> tuple[float | None, float | None, float | None]:
    line_values = [float(quote.line) for quote in quotes if quote.line is not None]
    price_values = [float(quote.price) for quote in quotes]

    if market == "h2h":
        implied_probs = [american_to_implied_prob(price) for price in price_values]
        probs = [float(prob) for prob in implied_probs if prob is not None]
        dispersion = float(pstdev(probs)) if len(probs) > 1 else None
        return (
            None,
            float(median(price_values)) if price_values else None,
            dispersion,
        )

    dispersion = float(pstdev(line_values)) if len(line_values) > 1 else None
    return (
        float(median(line_values)) if line_values else None,
        float(median(price_values)) if price_values else None,
        dispersion,
    )


def _compute_quote_delta(
    market: str,
    quote: OddsSnapshot,
    consensus_line: float | None,
    consensus_price: float | None,
) -> tuple[float | None, str]:
    if market in {"spreads", "totals"}:
        if quote.line is None or consensus_line is None:
            return None, "line"
        return float(quote.line) - float(consensus_line), "line"

    if consensus_price is None:
        return None, "implied_prob"
    consensus_prob = american_to_implied_prob(consensus_price)
    book_prob = american_to_implied_prob(quote.price)
    if consensus_prob is None or book_prob is None:
        return None, "implied_prob"
    return float(book_prob) - float(consensus_prob), "implied_prob"


def _delta_baseline_for_market(market: str) -> float:
    if market == "totals":
        return max(0.1, float(settings.dislocation_total_line_delta))
    if market == "h2h":
        return max(0.001, float(settings.dislocation_ml_implied_prob_delta))
    return max(0.1, float(settings.dislocation_spread_line_delta))


def _freshness_bucket(freshness_seconds: int | None, stale_threshold: int) -> str:
    if freshness_seconds is None:
        return "stale"
    if freshness_seconds <= max(60, stale_threshold // 2):
        return "fresh"
    if freshness_seconds <= stale_threshold:
        return "aging"
    return "stale"


def _compute_execution_rank(
    *,
    market: str,
    best_delta: float | None,
    books_considered: int,
    freshness_seconds: int | None,
    stale_threshold: int,
) -> int:
    delta = abs(float(best_delta or 0.0))
    baseline = _delta_baseline_for_market(market)
    delta_component = min(50.0, (delta / baseline) * 24.0)

    if freshness_seconds is None:
        freshness_component = 4.0
    elif freshness_seconds <= max(60, stale_threshold // 2):
        freshness_component = 30.0
    elif freshness_seconds <= stale_threshold:
        freshness_component = 20.0
    else:
        freshness_component = 8.0

    books_component = min(20.0, max(0.0, float(books_considered) * 2.5))
    rank = int(max(1, min(100, round(10.0 + delta_component + freshness_component + books_component))))
    return rank


def _actionable_reason(
    *,
    best_delta: float | None,
    books_considered: int,
    freshness_bucket: str,
    market: str,
) -> str:
    magnitude = abs(float(best_delta or 0.0))
    baseline = _delta_baseline_for_market(market)
    relative = magnitude / baseline if baseline > 0 else 0.0

    if relative >= 1.8 and freshness_bucket == "fresh" and books_considered >= 3:
        return "Large consensus gap with fresh pricing and broad book coverage."
    if relative >= 1.0 and freshness_bucket in {"fresh", "aging"}:
        return "Meaningful book dislocation relative to current consensus."
    if freshness_bucket == "stale":
        return "Potential edge but quote freshness is degraded."
    return "Moderate dislocation; validate timing and book availability."


async def get_clv_performance_summary(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_samples: int = 1,
    min_strength: int | None = None,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)

    stmt = (
        select(
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive_clv"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .outerjoin(Signal, Signal.id == ClvRecord.signal_id)
        .where(ClvRecord.computed_at >= cutoff)
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)

    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if min_strength is not None:
        stmt = stmt.where(func.coalesce(Signal.strength_score, 0) >= int(min_strength))

    stmt = (
        stmt.group_by(ClvRecord.signal_type, ClvRecord.market)
        .having(func.count(ClvRecord.id) >= max(1, int(min_samples)))
        .order_by(func.count(ClvRecord.id).desc(), ClvRecord.signal_type.asc(), ClvRecord.market.asc())
    )
    rows = (await db.execute(stmt)).mappings().all()

    return [
        {
            "signal_type": str(row["signal_type"]),
            "market": str(row["market"]),
            "count": int(row["count"] or 0),
            "pct_positive_clv": float(row["pct_positive_clv"] or 0.0),
            "avg_clv_line": float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None,
            "avg_clv_prob": float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None,
        }
        for row in rows
    ]


async def get_clv_postgame_recap(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    grain: str = "day",
    signal_type: str | None = None,
    market: str | None = None,
    min_samples: int = 1,
    min_strength: int | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    ready_cutoff = now - timedelta(minutes=settings.clv_minutes_after_commence)
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)
    bucket_expr = func.date_trunc(grain, func.timezone("UTC", Game.commence_time))

    stmt = (
        select(
            bucket_expr.label("period_start"),
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive_clv"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .join(Game, Game.event_id == ClvRecord.event_id)
        .outerjoin(Signal, Signal.id == ClvRecord.signal_id)
        .where(
            Game.commence_time >= cutoff,
            Game.commence_time <= ready_cutoff,
        )
    )

    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if sport_key:
        stmt = stmt.where(Game.sport_key == sport_key)
    if min_strength is not None:
        stmt = stmt.where(func.coalesce(Signal.strength_score, 0) >= int(min_strength))

    stmt = (
        stmt.group_by(bucket_expr, ClvRecord.signal_type, ClvRecord.market)
        .having(func.count(ClvRecord.id) >= max(1, int(min_samples)))
        .order_by(
            bucket_expr.desc(),
            func.count(ClvRecord.id).desc(),
            ClvRecord.signal_type.asc(),
            ClvRecord.market.asc(),
        )
    )
    rows = (await db.execute(stmt)).mappings().all()

    return {
        "days": int(days),
        "grain": grain,
        "rows": [
            {
                "period_start": _as_utc_datetime(row["period_start"]),
                "signal_type": str(row["signal_type"]),
                "market": str(row["market"]),
                "count": int(row["count"] or 0),
                "pct_positive_clv": float(row["pct_positive_clv"] or 0.0),
                "avg_clv_line": float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None,
                "avg_clv_prob": float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None,
            }
            for row in rows
        ],
    }


def _stability_ratio(avg_value: float | None, stddev_value: float | None) -> float | None:
    if avg_value is None or stddev_value is None:
        return None
    denominator = abs(float(avg_value))
    if denominator < 1e-9:
        return None
    return float(stddev_value) / denominator


def _stability_points(ratio: float | None) -> int:
    if ratio is None:
        return 4
    if ratio <= 1.0:
        return 20
    if ratio <= 1.5:
        return 14
    if ratio <= 2.0:
        return 9
    if ratio <= 3.0:
        return 5
    return 2


def _sample_points(count: int) -> int:
    if count >= 200:
        return 45
    if count >= 100:
        return 35
    if count >= 60:
        return 28
    if count >= 30:
        return 20
    if count >= 15:
        return 12
    return 6


def _edge_points(pct_positive: float) -> int:
    edge = abs(float(pct_positive) - 50.0)
    if edge >= 20.0:
        return 25
    if edge >= 15.0:
        return 20
    if edge >= 10.0:
        return 14
    if edge >= 5.0:
        return 8
    return 3


def _confidence_tier(
    *,
    count: int,
    pct_positive: float,
    confidence_score: int,
) -> str:
    if count >= 100 and confidence_score >= 70 and pct_positive >= 54.0:
        return "A"
    if count >= 30 and confidence_score >= 50 and pct_positive >= 52.0:
        return "B"
    return "C"


def _stability_label(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio <= 1.2:
        return "stable"
    if ratio <= 2.0:
        return "moderate"
    return "noisy"


async def get_clv_trust_scorecards(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_samples: int = 10,
    min_strength: int | None = None,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)

    stmt = (
        select(
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive_clv"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
            func.stddev_pop(ClvRecord.clv_line).label("stddev_clv_line"),
            func.stddev_pop(ClvRecord.clv_prob).label("stddev_clv_prob"),
        )
        .outerjoin(Signal, Signal.id == ClvRecord.signal_id)
        .where(ClvRecord.computed_at >= cutoff)
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)

    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if min_strength is not None:
        stmt = stmt.where(func.coalesce(Signal.strength_score, 0) >= int(min_strength))

    stmt = (
        stmt.group_by(ClvRecord.signal_type, ClvRecord.market)
        .having(func.count(ClvRecord.id) >= max(1, int(min_samples)))
    )

    rows = (await db.execute(stmt)).mappings().all()
    scorecards: list[dict[str, Any]] = []
    for row in rows:
        count = int(row["count"] or 0)
        pct_positive = float(row["pct_positive_clv"] or 0.0)
        avg_clv_line = float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None
        avg_clv_prob = float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None
        stddev_clv_line = float(row["stddev_clv_line"]) if row["stddev_clv_line"] is not None else None
        stddev_clv_prob = float(row["stddev_clv_prob"]) if row["stddev_clv_prob"] is not None else None

        line_ratio = _stability_ratio(avg_clv_line, stddev_clv_line)
        prob_ratio = _stability_ratio(avg_clv_prob, stddev_clv_prob)
        effective_ratio = (
            line_ratio
            if line_ratio is not None
            else prob_ratio
        )
        if line_ratio is not None and prob_ratio is not None:
            effective_ratio = min(line_ratio, prob_ratio)

        sample_component = _sample_points(count)
        edge_component = _edge_points(pct_positive)
        stability_component = _stability_points(effective_ratio)
        confidence_score = max(1, min(100, int(round(sample_component + edge_component + stability_component))))

        scorecards.append(
            {
                "signal_type": str(row["signal_type"]),
                "market": str(row["market"]),
                "count": count,
                "pct_positive_clv": pct_positive,
                "avg_clv_line": avg_clv_line,
                "avg_clv_prob": avg_clv_prob,
                "stddev_clv_line": stddev_clv_line,
                "stddev_clv_prob": stddev_clv_prob,
                "confidence_score": confidence_score,
                "confidence_tier": _confidence_tier(
                    count=count,
                    pct_positive=pct_positive,
                    confidence_score=confidence_score,
                ),
                "stability_ratio_line": line_ratio,
                "stability_ratio_prob": prob_ratio,
                "stability_label": _stability_label(effective_ratio),
                "score_components": {
                    "sample_points": sample_component,
                    "edge_points": edge_component,
                    "stability_points": stability_component,
                },
            }
        )

    scorecards.sort(
        key=lambda item: (
            int(item["confidence_score"]),
            int(item["count"]),
            str(item["signal_type"]),
            str(item["market"]),
        ),
        reverse=True,
    )
    return scorecards


async def get_clv_records_filtered(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    event_id: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    normalized_limit = _normalize_limit(limit)
    normalized_offset = max(0, int(offset))

    stmt = (
        select(
            ClvRecord.signal_id.label("signal_id"),
            ClvRecord.event_id.label("event_id"),
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            ClvRecord.outcome_name.label("outcome_name"),
            func.coalesce(Signal.strength_score, 0).label("strength_score"),
            ClvRecord.entry_line.label("entry_line"),
            ClvRecord.entry_price.label("entry_price"),
            ClvRecord.close_line.label("close_line"),
            ClvRecord.close_price.label("close_price"),
            ClvRecord.clv_line.label("clv_line"),
            ClvRecord.clv_prob.label("clv_prob"),
            ClvRecord.computed_at.label("computed_at"),
        )
        .outerjoin(Signal, Signal.id == ClvRecord.signal_id)
        .where(ClvRecord.computed_at >= cutoff)
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)

    if event_id:
        stmt = stmt.where(ClvRecord.event_id == event_id)
    if signal_type:
        stmt = stmt.where(ClvRecord.signal_type == signal_type)
    if market:
        stmt = stmt.where(ClvRecord.market == market)
    if min_strength is not None:
        stmt = stmt.where(func.coalesce(Signal.strength_score, 0) >= int(min_strength))

    stmt = stmt.order_by(ClvRecord.computed_at.desc()).limit(normalized_limit).offset(normalized_offset)
    rows = (await db.execute(stmt)).mappings().all()

    return [dict(row) for row in rows]


async def get_signal_quality_rows(
    db: AsyncSession,
    *,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    min_books_affected: int | None = None,
    max_dispersion: float | None = None,
    window_minutes_max: int | None = None,
    time_bucket: str | None = None,
    time_bucket_in: list[str] | None = None,
    created_after: datetime | None = None,
    days: int = 30,
    limit: int = 100,
    offset: int = 0,
    apply_alert_rules: bool = False,
    include_hidden: bool = True,
    connection: DiscordConnection | None = None,
) -> list[dict[str, Any]]:
    cutoff = created_after or (datetime.now(UTC) - timedelta(days=days))
    effective_min_strength = (
        int(min_strength)
        if min_strength is not None
        else max(1, int(settings.signal_filter_default_min_strength))
    )
    normalized_limit = _normalize_limit(limit)
    normalized_offset = max(0, int(offset))

    stmt = (
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.strength_score >= effective_min_strength,
        )
        .order_by(Signal.created_at.desc())
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == Signal.event_id).where(Game.sport_key == sport_key)

    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if market:
        stmt = stmt.where(Signal.market == market)
    if min_books_affected is not None:
        stmt = stmt.where(Signal.books_affected >= int(min_books_affected))
    if window_minutes_max is not None:
        stmt = stmt.where(Signal.window_minutes <= int(window_minutes_max))
    if time_bucket is not None:
        if time_bucket == "UNKNOWN":
            stmt = stmt.where(or_(Signal.time_bucket == "UNKNOWN", Signal.time_bucket.is_(None)))
        else:
            stmt = stmt.where(Signal.time_bucket == time_bucket)
    if time_bucket_in:
        includes_unknown = "UNKNOWN" in time_bucket_in
        explicit = [bucket for bucket in time_bucket_in if bucket != "UNKNOWN"]
        if includes_unknown and explicit:
            stmt = stmt.where(
                or_(
                    Signal.time_bucket.in_(explicit),
                    Signal.time_bucket == "UNKNOWN",
                    Signal.time_bucket.is_(None),
                )
            )
        elif includes_unknown:
            stmt = stmt.where(or_(Signal.time_bucket == "UNKNOWN", Signal.time_bucket.is_(None)))
        else:
            stmt = stmt.where(Signal.time_bucket.in_(explicit))
    if not settings.time_bucket_expose_inplay:
        stmt = stmt.where(or_(Signal.time_bucket.is_(None), Signal.time_bucket != "INPLAY"))
    if max_dispersion is not None:
        dispersion_expr = cast(Signal.metadata_json["dispersion"].astext, Float)
        stmt = stmt.where(
            or_(
                Signal.signal_type != "DISLOCATION",
                dispersion_expr.is_(None),
                dispersion_expr <= float(max_dispersion),
            )
        )

    stmt = stmt.limit(normalized_limit).offset(normalized_offset)
    rows = (await db.execute(stmt)).scalars().all()
    event_ids = sorted({signal.event_id for signal in rows if signal.event_id})
    game_map: dict[str, Game] = {}
    if event_ids:
        games_stmt = select(Game).where(Game.event_id.in_(event_ids))
        games = (await db.execute(games_stmt)).scalars().all()
        game_map = {game.event_id: game for game in games}

    payload: list[dict[str, Any]] = []
    for signal in rows:
        metadata = signal.metadata_json or {}
        game = game_map.get(signal.event_id)
        game_label = None
        game_commence_time = None
        if game is not None:
            game_label = f"{game.away_team} @ {game.home_team}"
            game_commence_time = game.commence_time
        alert_decision, alert_reason = _resolve_signal_alert_decision(
            signal,
            connection=connection,
            apply_alert_rules=apply_alert_rules,
        )
        freshness_seconds, freshness_bucket, _stale_threshold = _signal_freshness(signal)
        lifecycle_stage, lifecycle_reason = _resolve_signal_lifecycle(
            alert_decision=alert_decision,
            alert_reason=alert_reason,
            freshness_bucket=freshness_bucket,
            freshness_seconds=freshness_seconds,
            apply_alert_rules=apply_alert_rules,
        )
        if not include_hidden and alert_decision == "hidden":
            continue
        minutes_to_tip = _safe_float(metadata.get("minutes_to_tip"))
        resolved_time_bucket = signal.time_bucket or compute_time_bucket(minutes_to_tip)
        if not settings.time_bucket_expose_inplay and resolved_time_bucket == "INPLAY":
            resolved_time_bucket = "UNKNOWN"
        payload.append(
            {
                "id": signal.id,
                "event_id": signal.event_id,
                "game_label": game_label,
                "game_commence_time": game_commence_time,
                "market": signal.market,
                "signal_type": signal.signal_type,
                "display_type": signal_display_type(signal.signal_type),
                "direction": signal.direction,
                "strength_score": signal.strength_score,
                "time_bucket": resolved_time_bucket,
                "books_affected": signal.books_affected,
                "window_minutes": signal.window_minutes,
                "created_at": signal.created_at,
                "outcome_name": metadata.get("outcome_name"),
                "book_key": metadata.get("book_key"),
                "delta": _safe_float(metadata.get("delta")),
                "dispersion": _safe_float(metadata.get("dispersion")),
                "freshness_seconds": freshness_seconds,
                "freshness_bucket": freshness_bucket,
                "lifecycle_stage": lifecycle_stage,
                "lifecycle_reason": lifecycle_reason,
                "alert_decision": alert_decision,
                "alert_reason": alert_reason,
                "metadata": metadata,
            }
        )
    return payload


async def get_signal_lifecycle_summary(
    db: AsyncSession,
    *,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    time_bucket: str | None = None,
    days: int = 7,
    apply_alert_rules: bool = True,
    connection: DiscordConnection | None = None,
) -> dict[str, Any]:
    cutoff = created_after or (datetime.now(UTC) - timedelta(days=days))
    effective_min_strength = (
        int(min_strength)
        if min_strength is not None
        else max(1, int(settings.signal_filter_default_min_strength))
    )
    stmt = (
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.strength_score >= effective_min_strength,
        )
        .order_by(Signal.created_at.desc())
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == Signal.event_id).where(Game.sport_key == sport_key)
    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if market:
        stmt = stmt.where(Signal.market == market)
    if created_before is not None:
        stmt = stmt.where(Signal.created_at < created_before)
    if time_bucket is not None:
        if time_bucket == "UNKNOWN":
            stmt = stmt.where(or_(Signal.time_bucket == "UNKNOWN", Signal.time_bucket.is_(None)))
        else:
            stmt = stmt.where(Signal.time_bucket == time_bucket)
    if not settings.time_bucket_expose_inplay:
        stmt = stmt.where(or_(Signal.time_bucket.is_(None), Signal.time_bucket != "INPLAY"))

    signals = (await db.execute(stmt)).scalars().all()
    total_detected = len(signals)
    if total_detected == 0:
        return {
            "days": int(days),
            "total_detected": 0,
            "eligible_signals": 0,
            "sent_signals": 0,
            "filtered_signals": 0,
            "stale_signals": 0,
            "not_sent_signals": 0,
            "top_filtered_reasons": [],
        }

    eligible_signals = 0
    sent_signals = 0
    filtered_signals = 0
    stale_signals = 0
    not_sent_signals = 0
    filtered_reasons: Counter[str] = Counter()

    for signal in signals:
        alert_decision, alert_reason = _resolve_signal_alert_decision(
            signal,
            connection=connection,
            apply_alert_rules=apply_alert_rules,
        )
        freshness_seconds, freshness_bucket, _stale_threshold = _signal_freshness(signal)
        lifecycle_stage, lifecycle_reason = _resolve_signal_lifecycle(
            alert_decision=alert_decision,
            alert_reason=alert_reason,
            freshness_bucket=freshness_bucket,
            freshness_seconds=freshness_seconds,
            apply_alert_rules=apply_alert_rules,
        )

        if alert_decision != "hidden":
            eligible_signals += 1
        if lifecycle_stage == "sent":
            sent_signals += 1
        elif lifecycle_stage == "filtered":
            filtered_signals += 1
            filtered_reasons[lifecycle_reason] += 1
            not_sent_signals += 1
        elif lifecycle_stage == "stale":
            stale_signals += 1
            not_sent_signals += 1

    top_filtered_reasons = [
        {"reason": reason, "count": int(count)}
        for reason, count in filtered_reasons.most_common(5)
    ]
    return {
        "days": int(days),
        "total_detected": total_detected,
        "eligible_signals": eligible_signals,
        "sent_signals": sent_signals,
        "filtered_signals": filtered_signals,
        "stale_signals": stale_signals,
        "not_sent_signals": not_sent_signals,
        "top_filtered_reasons": top_filtered_reasons,
    }


async def get_signal_quality_weekly_summary(
    db: AsyncSession,
    *,
    days: int = 7,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    apply_alert_rules: bool = True,
    connection: DiscordConnection | None = None,
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    effective_min_strength = (
        int(min_strength)
        if min_strength is not None
        else max(1, int(settings.signal_filter_default_min_strength))
    )
    stmt = (
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.strength_score >= effective_min_strength,
        )
        .order_by(Signal.created_at.desc())
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == Signal.event_id).where(Game.sport_key == sport_key)
    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if market:
        stmt = stmt.where(Signal.market == market)

    signals = (await db.execute(stmt)).scalars().all()
    total_signals = len(signals)
    if total_signals == 0:
        return {
            "days": int(days),
            "total_signals": 0,
            "eligible_signals": 0,
            "hidden_signals": 0,
            "sent_rate_pct": 0.0,
            "avg_strength": None,
            "clv_samples": 0,
            "clv_pct_positive": 0.0,
            "top_hidden_reason": None,
        }

    eligible_signal_ids: set[UUID] = set()
    hidden_reasons: Counter[str] = Counter()
    strengths_total = 0
    eligible_signals = 0

    for signal in signals:
        strengths_total += int(signal.strength_score)
        decision, reason = _resolve_signal_alert_decision(
            signal,
            connection=connection,
            apply_alert_rules=apply_alert_rules,
        )
        if decision == "sent":
            eligible_signals += 1
            eligible_signal_ids.add(signal.id)
        else:
            hidden_reasons[reason] += 1

    hidden_signals = total_signals - eligible_signals
    sent_rate_pct = (eligible_signals / total_signals) * 100.0 if total_signals > 0 else 0.0
    avg_strength = strengths_total / total_signals if total_signals > 0 else None
    top_hidden_reason = hidden_reasons.most_common(1)[0][0] if hidden_reasons else None

    clv_positive = 0
    clv_samples = 0
    if eligible_signal_ids:
        clv_stmt = select(ClvRecord.signal_id, ClvRecord.clv_line, ClvRecord.clv_prob).where(
            ClvRecord.signal_id.in_(eligible_signal_ids),
            ClvRecord.computed_at >= cutoff,
        )
        clv_rows = (await db.execute(clv_stmt)).all()
        clv_samples = len(clv_rows)
        for _signal_id, clv_line, clv_prob in clv_rows:
            if (clv_line is not None and float(clv_line) > 0) or (clv_prob is not None and float(clv_prob) > 0):
                clv_positive += 1

    clv_pct_positive = (clv_positive / clv_samples) * 100.0 if clv_samples > 0 else 0.0
    return {
        "days": int(days),
        "total_signals": total_signals,
        "eligible_signals": eligible_signals,
        "hidden_signals": hidden_signals,
        "sent_rate_pct": round(float(sent_rate_pct), 2),
        "avg_strength": round(float(avg_strength), 2) if avg_strength is not None else None,
        "clv_samples": clv_samples,
        "clv_pct_positive": round(float(clv_pct_positive), 2),
        "top_hidden_reason": top_hidden_reason,
    }


async def get_clv_teaser(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    total_records_stmt = select(func.count(ClvRecord.id)).where(ClvRecord.computed_at >= cutoff)
    if sport_key:
        total_records_stmt = total_records_stmt.join(Game, Game.event_id == ClvRecord.event_id).where(
            Game.sport_key == sport_key
        )
    total_records = int((await db.execute(total_records_stmt)).scalar() or 0)
    rows = await get_clv_performance_summary(
        db,
        days=days,
        sport_key=sport_key,
        min_samples=1,
        min_strength=None,
    )
    ranked = sorted(rows, key=lambda row: (row["count"], row["signal_type"], row["market"]), reverse=True)
    return {
        "days": int(days),
        "total_records": total_records,
        "rows": ranked[:8],
    }


async def _latest_consensus(
    db: AsyncSession,
    *,
    event_id: str,
    market: str,
    outcome_name: str,
) -> MarketConsensusSnapshot | None:
    stmt = (
        select(MarketConsensusSnapshot)
        .where(
            MarketConsensusSnapshot.event_id == event_id,
            MarketConsensusSnapshot.market == market,
            MarketConsensusSnapshot.outcome_name == outcome_name,
        )
        .order_by(MarketConsensusSnapshot.fetched_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _latest_quotes_for_outcome(
    db: AsyncSession,
    *,
    event_id: str,
    market: str,
    outcome_name: str | None,
) -> list[OddsSnapshot]:
    filters = [OddsSnapshot.event_id == event_id, OddsSnapshot.market == market]
    if outcome_name:
        filters.append(OddsSnapshot.outcome_name == outcome_name)

    stmt = (
        select(OddsSnapshot)
        .where(*filters)
        .order_by(OddsSnapshot.sportsbook_key.asc(), OddsSnapshot.fetched_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    latest_by_book: dict[str, OddsSnapshot] = {}
    for row in rows:
        if row.sportsbook_key in latest_by_book:
            continue
        latest_by_book[row.sportsbook_key] = row
    return list(latest_by_book.values())


async def _resolve_signal_outcome(
    db: AsyncSession,
    *,
    signal: Signal,
) -> str | None:
    metadata = signal.metadata_json or {}
    outcome_name = metadata.get("outcome_name")
    if isinstance(outcome_name, str) and outcome_name.strip():
        return outcome_name.strip()

    fallback_stmt = (
        select(OddsSnapshot.outcome_name, func.count(OddsSnapshot.id).label("rows_count"))
        .where(
            OddsSnapshot.event_id == signal.event_id,
            OddsSnapshot.market == signal.market,
        )
        .group_by(OddsSnapshot.outcome_name)
        .order_by(desc("rows_count"), OddsSnapshot.outcome_name.asc())
        .limit(1)
    )
    fallback = (await db.execute(fallback_stmt)).first()
    if fallback is None:
        return None
    return str(fallback[0])


async def get_actionable_book_card(
    db: AsyncSession,
    *,
    event_id: str,
    signal_id: UUID,
    max_books: int | None = None,
) -> dict[str, Any] | None:
    signal = await db.get(Signal, signal_id)
    if signal is None or signal.event_id != event_id:
        return None

    outcome_name = await _resolve_signal_outcome(db, signal=signal)
    quotes = await _latest_quotes_for_outcome(
        db,
        event_id=event_id,
        market=signal.market,
        outcome_name=outcome_name,
    )

    consensus_row = None
    if outcome_name:
        consensus_row = await _latest_consensus(
            db,
            event_id=event_id,
            market=signal.market,
            outcome_name=outcome_name,
        )

    if consensus_row:
        consensus_line = (
            float(consensus_row.consensus_line) if consensus_row.consensus_line is not None else None
        )
        consensus_price = (
            float(consensus_row.consensus_price) if consensus_row.consensus_price is not None else None
        )
        dispersion = float(consensus_row.dispersion) if consensus_row.dispersion is not None else None
        consensus_source = "persisted_consensus"
    else:
        consensus_line, consensus_price, dispersion = _derive_consensus_from_quotes(signal.market, quotes)
        consensus_source = "derived_from_latest_books"

    delta_type = "line" if signal.market in {"spreads", "totals"} else "implied_prob"
    if not quotes:
        return {
            "event_id": event_id,
            "signal_id": signal.id,
            "signal_type": signal.signal_type,
            "display_type": signal_display_type(signal.signal_type),
            "market": signal.market,
            "outcome_name": outcome_name,
            "direction": signal.direction,
            "strength_score": signal.strength_score,
            "consensus_line": consensus_line,
            "consensus_price": consensus_price,
            "dispersion": dispersion,
            "consensus_source": "none",
            "best_book_key": None,
            "best_line": None,
            "best_price": None,
            "best_delta": None,
            "delta_type": delta_type,
            "fetched_at": None,
            "freshness_seconds": None,
            "freshness_bucket": "stale",
            "is_stale": True,
            "execution_rank": 1,
            "actionable_reason": "No eligible live quotes found for this signal context.",
            "books_considered": 0,
            "top_books": [],
            "quotes": [],
        }

    quotes_payload: list[dict[str, Any]] = []
    for quote in quotes:
        delta, _delta_type = _compute_quote_delta(signal.market, quote, consensus_line, consensus_price)
        quotes_payload.append(
            {
                "sportsbook_key": quote.sportsbook_key,
                "line": float(quote.line) if quote.line is not None else None,
                "price": int(quote.price),
                "fetched_at": quote.fetched_at,
                "delta": delta,
            }
        )

    quotes_payload.sort(
        key=lambda item: (
            abs(float(item["delta"])) if item["delta"] is not None else -1.0,
            item["fetched_at"],
            item["sportsbook_key"],
        ),
        reverse=True,
        )

    max_quotes = max_books if max_books is not None else settings.actionable_book_max_books
    normalized_max_quotes = max(1, min(int(max_quotes), 20))
    quotes_payload = quotes_payload[:normalized_max_quotes]
    top_books = quotes_payload[:3]

    best_quote = quotes_payload[0] if quotes_payload else None
    now = datetime.now(UTC)
    freshness_seconds = None
    if best_quote and isinstance(best_quote.get("fetched_at"), datetime):
        freshness_seconds = max(
            0,
            int((now - best_quote["fetched_at"]).total_seconds()),
        )
    stale_threshold = max(180, int(settings.odds_poll_interval_seconds) * 3)
    freshness_bucket = _freshness_bucket(freshness_seconds, stale_threshold)
    is_stale = freshness_seconds is None or freshness_seconds > stale_threshold
    execution_rank = _compute_execution_rank(
        market=signal.market,
        best_delta=best_quote.get("delta") if best_quote else None,
        books_considered=len(quotes_payload),
        freshness_seconds=freshness_seconds,
        stale_threshold=stale_threshold,
    )
    actionable_reason = _actionable_reason(
        best_delta=best_quote.get("delta") if best_quote else None,
        books_considered=len(quotes_payload),
        freshness_bucket=freshness_bucket,
        market=signal.market,
    )

    return {
        "event_id": event_id,
        "signal_id": signal.id,
        "signal_type": signal.signal_type,
        "display_type": signal_display_type(signal.signal_type),
        "market": signal.market,
        "outcome_name": outcome_name,
        "direction": signal.direction,
        "strength_score": signal.strength_score,
        "consensus_line": consensus_line,
        "consensus_price": consensus_price,
        "dispersion": dispersion,
        "consensus_source": consensus_source,
        "best_book_key": best_quote.get("sportsbook_key") if best_quote else None,
        "best_line": best_quote.get("line") if best_quote else None,
        "best_price": best_quote.get("price") if best_quote else None,
        "best_delta": best_quote.get("delta") if best_quote else None,
        "delta_type": delta_type,
        "fetched_at": best_quote.get("fetched_at") if best_quote else None,
        "freshness_seconds": freshness_seconds,
        "freshness_bucket": freshness_bucket,
        "is_stale": is_stale,
        "execution_rank": execution_rank,
        "actionable_reason": actionable_reason,
        "books_considered": len(quotes_payload),
        "top_books": top_books,
        "quotes": quotes_payload,
    }


async def get_actionable_book_cards_batch(
    db: AsyncSession,
    *,
    event_id: str,
    signal_ids: list[UUID],
    max_books: int | None = None,
) -> list[dict[str, Any]]:
    if not signal_ids:
        return []

    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for signal_id in signal_ids:
        if signal_id in seen:
            continue
        seen.add(signal_id)
        unique_ids.append(signal_id)
        if len(unique_ids) >= 20:
            break

    cards: list[dict[str, Any]] = []
    for signal_id in unique_ids:
        card = await get_actionable_book_card(
            db,
            event_id=event_id,
            signal_id=signal_id,
            max_books=max_books,
        )
        if card is None:
            continue
        cards.append(card)
    return cards


async def _clv_prior_by_signal_market(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
) -> dict[tuple[str, str], dict[str, float | int]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)
    stmt = (
        select(
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("samples"),
            (func.avg(positive_expr) * 100.0).label("pct_positive"),
        )
        .where(ClvRecord.computed_at >= cutoff)
        .group_by(ClvRecord.signal_type, ClvRecord.market)
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == ClvRecord.event_id).where(Game.sport_key == sport_key)
    rows = (await db.execute(stmt)).mappings().all()
    payload: dict[tuple[str, str], dict[str, float | int]] = {}
    for row in rows:
        key = (str(row["signal_type"]), str(row["market"]))
        payload[key] = {
            "samples": int(row["samples"] or 0),
            "pct_positive": float(row["pct_positive"] or 0.0),
        }
    return payload


def _compute_opportunity_score(
    *,
    market: str,
    strength_score: int,
    execution_rank: int,
    best_delta: float | None,
    books_considered: int,
    freshness_bucket: str,
    clv_prior_pct_positive: float | None,
    clv_prior_samples: int | None,
    dispersion: float | None,
) -> tuple[int, dict[str, int], str]:
    baseline = _delta_baseline_for_market(market)
    delta_ratio = abs(float(best_delta or 0.0)) / baseline if baseline > 0 else 0.0
    delta_component = min(20.0, delta_ratio * 8.0)
    strength_component = min(45.0, max(0.0, float(strength_score) * 0.45))
    execution_component = min(22.0, max(0.0, float(execution_rank) * 0.22))
    books_component = min(8.0, max(0.0, float(books_considered) * 1.6))

    freshness_component = 0.0
    if freshness_bucket == "fresh":
        freshness_component = 8.0
    elif freshness_bucket == "aging":
        freshness_component = 3.0
    else:
        freshness_component = -12.0

    clv_component = 0.0
    if clv_prior_pct_positive is not None and clv_prior_samples is not None and clv_prior_samples >= 10:
        clv_component = max(-8.0, min(8.0, (float(clv_prior_pct_positive) - 50.0) / 3.0))

    dispersion_penalty = 0.0
    if dispersion is not None and market in {"spreads", "totals"}:
        if dispersion > 1.5:
            dispersion_penalty = -6.0
        elif dispersion > 1.0:
            dispersion_penalty = -3.0

    score = (
        strength_component
        + execution_component
        + delta_component
        + books_component
        + freshness_component
        + clv_component
        + dispersion_penalty
    )
    normalized = int(max(1, min(100, round(score))))
    stale_cap_penalty = 0
    if freshness_bucket == "stale":
        # Keep stale quotes visible when requested, but prevent them from outranking live opportunities.
        capped = min(69, normalized)
        stale_cap_penalty = capped - normalized
        normalized = capped

    score_components = {
        "strength": int(round(strength_component)),
        "execution": int(round(execution_component)),
        "delta": int(round(delta_component)),
        "books": int(round(books_component)),
        "freshness": int(round(freshness_component)),
        "clv_prior": int(round(clv_component)),
        "dispersion_penalty": int(round(dispersion_penalty)),
        "stale_cap_penalty": int(stale_cap_penalty),
    }
    score_summary = (
        f"Strength {score_components['strength']} + Execution {score_components['execution']} + "
        f"Delta {score_components['delta']} + Books {score_components['books']} + "
        f"Freshness {score_components['freshness']} + CLV {score_components['clv_prior']} + "
        f"Dispersion {score_components['dispersion_penalty']} + StaleCap {score_components['stale_cap_penalty']}"
    )
    return normalized, score_components, score_summary


def _compute_context_score(context_scaffold: dict[str, Any] | None) -> int | None:
    if not isinstance(context_scaffold, dict):
        return None
    components = context_scaffold.get("components")
    if not isinstance(components, list):
        return None

    by_name: dict[str, int] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        name = str(component.get("component") or "").strip().lower()
        if not name:
            continue
        raw_score = component.get("score")
        if raw_score is None:
            continue
        parsed = _safe_float(raw_score)
        if parsed is None:
            continue
        by_name[name] = max(0, min(100, int(round(parsed))))

    weighted_inputs = [
        ("injuries", float(settings.context_score_weight_injuries)),
        ("player_props", float(settings.context_score_weight_player_props)),
        ("pace", float(settings.context_score_weight_pace)),
        ("cross_market", float(settings.context_score_weight_cross_market)),
    ]
    available: list[tuple[int, float]] = []
    for name, weight in weighted_inputs:
        score = by_name.get(name)
        if score is None:
            continue
        available.append((score, max(0.0, weight)))

    if not available:
        return None

    weight_total = sum(weight for _score, weight in available)
    if weight_total <= 0:
        return int(round(sum(score for score, _weight in available) / len(available)))

    weighted_score = sum(score * weight for score, weight in available) / weight_total
    return max(1, min(100, int(round(weighted_score))))


def _compute_blended_score(*, opportunity_score: int, context_score: int | None) -> int | None:
    if context_score is None:
        return None
    opp_weight = max(0.0, float(settings.context_score_blend_weight_opportunity))
    ctx_weight = max(0.0, float(settings.context_score_blend_weight_context))
    if opp_weight <= 0 and ctx_weight <= 0:
        opp_weight = 0.8
        ctx_weight = 0.2
    weight_total = opp_weight + ctx_weight
    if weight_total <= 0:
        return opportunity_score
    blended = ((float(opportunity_score) * opp_weight) + (float(context_score) * ctx_weight)) / weight_total
    return max(1, min(100, int(round(blended))))


def _opportunity_status(*, score: int, freshness_bucket: str) -> str:
    if freshness_bucket == "stale":
        return "stale"
    if score >= 75:
        return "actionable"
    return "monitor"


def _opportunity_status_priority(status: str) -> int:
    if status == "actionable":
        return 3
    if status == "monitor":
        return 2
    return 1


def _opportunity_reason_tags(
    *,
    signal_type: str,
    market: str,
    best_delta: float | None,
    books_considered: int,
    freshness_bucket: str,
    dispersion: float | None,
    clv_prior_pct_positive: float | None,
    clv_prior_samples: int | None,
) -> list[str]:
    tags: list[str] = [signal_type]
    baseline = _delta_baseline_for_market(market)
    delta_ratio = abs(float(best_delta or 0.0)) / baseline if baseline > 0 else 0.0
    if delta_ratio >= 1.5:
        tags.append("LARGE_DELTA")
    elif delta_ratio >= 1.0:
        tags.append("MEANINGFUL_DELTA")
    if books_considered >= 5:
        tags.append("MULTI_BOOK")
    if freshness_bucket == "fresh":
        tags.append("FRESH_QUOTE")
    elif freshness_bucket == "stale":
        tags.append("STALE_QUOTE")
    if dispersion is not None and dispersion <= 0.5 and market in {"spreads", "totals"}:
        tags.append("LOW_DISPERSION")
    if clv_prior_pct_positive is not None and clv_prior_samples is not None and clv_prior_samples >= 10:
        if clv_prior_pct_positive >= 55.0:
            tags.append("POSITIVE_CLV_PRIOR")
        elif clv_prior_pct_positive <= 45.0:
            tags.append("WEAK_CLV_PRIOR")
    return tags


def _compute_market_width(market: str, quotes: list[dict[str, Any]]) -> float | None:
    if not quotes:
        return None
    if market in {"spreads", "totals"}:
        lines = [_safe_float(quote.get("line")) for quote in quotes]
        line_values = [float(line) for line in lines if line is not None]
        if len(line_values) < 2:
            return None
        return float(max(line_values) - min(line_values))

    probs: list[float] = []
    for quote in quotes:
        price = _safe_float(quote.get("price"))
        if price is None:
            continue
        implied = american_to_implied_prob(price)
        if implied is None:
            continue
        probs.append(float(implied))
    if len(probs) < 2:
        return None
    return float(max(probs) - min(probs))


async def get_best_opportunities(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    min_edge: float | None = None,
    max_width: float | None = None,
    limit: int = 10,
    include_stale: bool = False,
) -> list[dict[str, Any]]:
    effective_min_strength = (
        int(min_strength)
        if min_strength is not None
        else max(1, int(settings.signal_filter_default_min_strength))
    )
    normalized_limit = max(1, min(int(limit), 50))
    candidate_limit = max(20, min(150, normalized_limit * 6))
    cutoff = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.strength_score >= effective_min_strength,
        )
        .order_by(Signal.created_at.desc(), Signal.strength_score.desc())
        .limit(candidate_limit)
    )
    if sport_key:
        stmt = stmt.join(Game, Game.event_id == Signal.event_id).where(Game.sport_key == sport_key)
    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if market:
        stmt = stmt.where(Signal.market == market)
    stmt = apply_structural_core_query_filters(
        stmt,
        signal_model=Signal,
        context="get_best_opportunities",
        min_strength=effective_min_strength,
    )

    signals = (await db.execute(stmt)).scalars().all()
    if not signals:
        return []

    event_ids = sorted({signal.event_id for signal in signals if signal.event_id})
    game_map: dict[str, Game] = {}
    if event_ids:
        games_stmt = select(Game).where(Game.event_id.in_(event_ids))
        games = (await db.execute(games_stmt)).scalars().all()
        game_map = {game.event_id: game for game in games}

    context_scaffold_by_event: dict[str, dict[str, Any] | None] = {}
    if event_ids:
        async def _fetch_context(event_id: str) -> tuple[str, dict[str, Any] | None]:
            try:
                return event_id, await build_context_score(db, event_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Context score build failed; proceeding without context blend for event",
                    exc_info=True,
                    extra={"event_id": event_id},
                )
                return event_id, None

        context_pairs = await asyncio.gather(*(_fetch_context(event_id) for event_id in event_ids))
        context_scaffold_by_event = {event_id: payload for event_id, payload in context_pairs}

    clv_prior_map = await _clv_prior_by_signal_market(db, days=max(days, 30), sport_key=sport_key)
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for signal in signals:
        card = await get_actionable_book_card(
            db,
            event_id=signal.event_id,
            signal_id=signal.id,
            max_books=settings.actionable_book_max_books,
        )
        if card is None or int(card.get("books_considered") or 0) <= 0:
            continue

        best_delta = _safe_float(card.get("best_delta"))
        edge_magnitude = abs(float(best_delta)) if best_delta is not None else 0.0
        delta_type = str(card.get("delta_type") or "line")
        best_edge_line = edge_magnitude if delta_type == "line" else None
        best_edge_prob = edge_magnitude if delta_type == "implied_prob" else None
        market_width = _compute_market_width(signal.market, card.get("quotes") or [])

        if min_edge is not None and edge_magnitude < float(min_edge):
            continue
        if max_width is not None:
            if market_width is None or market_width > float(max_width):
                continue

        prior = clv_prior_map.get((signal.signal_type, signal.market))
        prior_samples = int(prior["samples"]) if prior is not None else None
        prior_pct = float(prior["pct_positive"]) if prior is not None else None
        if not is_structural_core_visible(
            signal_type=signal.signal_type,
            market=signal.market,
            strength_score=signal.strength_score,
            min_samples=prior_samples,
            context="get_best_opportunities",
        ):
            continue
        opportunity_score, score_components, score_summary = _compute_opportunity_score(
            market=signal.market,
            strength_score=int(signal.strength_score),
            execution_rank=int(card.get("execution_rank") or 1),
            best_delta=best_delta,
            books_considered=int(card.get("books_considered") or 0),
            freshness_bucket=str(card.get("freshness_bucket") or "stale"),
            clv_prior_pct_positive=prior_pct,
            clv_prior_samples=prior_samples,
            dispersion=_safe_float(card.get("dispersion")),
        )
        context_score = _compute_context_score(context_scaffold_by_event.get(signal.event_id))
        blended_score = _compute_blended_score(
            opportunity_score=opportunity_score,
            context_score=context_score,
        )
        use_blended = bool(settings.context_score_blend_enabled and blended_score is not None)
        freshness_bucket = str(card.get("freshness_bucket") or "stale")
        ranking_score = int(blended_score if use_blended else opportunity_score)
        if freshness_bucket == "stale":
            ranking_score = min(69, ranking_score)
        score_basis = "blended" if use_blended else "opportunity"
        status = _opportunity_status(
            score=ranking_score,
            freshness_bucket=freshness_bucket,
        )
        tags = _opportunity_reason_tags(
            signal_type=signal.signal_type,
            market=signal.market,
            best_delta=best_delta,
            books_considered=int(card.get("books_considered") or 0),
            freshness_bucket=freshness_bucket,
            dispersion=_safe_float(card.get("dispersion")),
            clv_prior_pct_positive=prior_pct,
            clv_prior_samples=prior_samples,
        )

        game = game_map.get(signal.event_id)
        outcome_name = str(card.get("outcome_name") or "")
        row = {
            "signal_id": signal.id,
            "event_id": signal.event_id,
            "game_label": (f"{game.away_team} @ {game.home_team}" if game is not None else None),
            "game_commence_time": game.commence_time if game is not None else None,
            "signal_type": signal.signal_type,
            "display_type": signal_display_type(signal.signal_type),
            "market": signal.market,
            "outcome_name": (outcome_name or None),
            "direction": signal.direction,
            "strength_score": int(signal.strength_score),
            "created_at": signal.created_at,
            "best_book_key": card.get("best_book_key"),
            "best_line": _safe_float(card.get("best_line")),
            "best_price": (
                int(card["best_price"])
                if card.get("best_price") is not None
                else None
            ),
            "consensus_line": _safe_float(card.get("consensus_line")),
            "consensus_price": _safe_float(card.get("consensus_price")),
            "best_delta": best_delta,
            "best_edge_line": best_edge_line,
            "best_edge_prob": best_edge_prob,
            "market_width": market_width,
            "delta_type": delta_type,
            "books_considered": int(card.get("books_considered") or 0),
            "freshness_seconds": (
                int(card["freshness_seconds"])
                if card.get("freshness_seconds") is not None
                else None
            ),
            "freshness_bucket": str(card.get("freshness_bucket") or "stale"),
            "execution_rank": int(card.get("execution_rank") or 1),
            "clv_prior_samples": prior_samples,
            "clv_prior_pct_positive": prior_pct,
            "opportunity_score": opportunity_score,
            "context_score": context_score,
            "blended_score": blended_score,
            "ranking_score": ranking_score,
            "score_basis": score_basis,
            "score_components": score_components,
            "score_summary": score_summary,
            "opportunity_status": status,
            "reason_tags": tags,
            "actionable_reason": str(card.get("actionable_reason") or "No rationale available."),
        }

        dedupe_key = (
            str(signal.event_id),
            str(signal.market),
            outcome_name,
            str(signal.direction),
        )
        existing = deduped.get(dedupe_key)
        if existing is None:
            deduped[dedupe_key] = row
        else:
            incoming_rank = (
                _opportunity_status_priority(str(row["opportunity_status"])),
                int(row["ranking_score"]),
                int(row["strength_score"]),
                int(row["execution_rank"]),
                row["created_at"],
            )
            existing_rank = (
                _opportunity_status_priority(str(existing["opportunity_status"])),
                int(existing["ranking_score"]),
                int(existing["strength_score"]),
                int(existing["execution_rank"]),
                existing["created_at"],
            )
            if incoming_rank > existing_rank:
                deduped[dedupe_key] = row

    opportunities = list(deduped.values())
    if not include_stale:
        opportunities = [row for row in opportunities if str(row["freshness_bucket"]) != "stale"]

    opportunities.sort(
        key=lambda item: (
            _opportunity_status_priority(str(item["opportunity_status"])),
            int(item["ranking_score"]),
            int(item["strength_score"]),
            int(item["execution_rank"]),
            item["created_at"],
            str(item["event_id"]),
        ),
        reverse=True,
    )
    return opportunities[:normalized_limit]


async def get_delayed_opportunity_teaser(
    db: AsyncSession,
    *,
    days: int,
    sport_key: str | None = None,
    signal_type: str | None = None,
    market: str | None = None,
    min_strength: int | None = None,
    limit: int = 3,
    delay_minutes: int | None = None,
    include_stale: bool = True,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 20))
    candidate_limit = max(50, min(150, normalized_limit * 10))
    effective_delay_minutes = (
        max(0, int(delay_minutes))
        if delay_minutes is not None
        else max(0, int(settings.free_delay_minutes))
    )
    delay_cutoff = datetime.now(UTC) - timedelta(minutes=effective_delay_minutes)

    opportunities = await get_best_opportunities(
        db,
        days=days,
        sport_key=sport_key,
        signal_type=signal_type,
        market=market,
        min_strength=min_strength,
        limit=candidate_limit,
        include_stale=include_stale,
    )
    delayed = [row for row in opportunities if row.get("created_at") is not None and row["created_at"] <= delay_cutoff]
    delayed.sort(
        key=lambda item: (
            _opportunity_status_priority(str(item["opportunity_status"])),
            int(item["opportunity_score"]),
            item["created_at"],
        ),
        reverse=True,
    )

    redacted_rows: list[dict[str, Any]] = []
    for row in delayed[:normalized_limit]:
        redacted_rows.append(
            {
                "event_id": row["event_id"],
                "game_label": row.get("game_label"),
                "game_commence_time": row.get("game_commence_time"),
                "signal_type": row["signal_type"],
                "display_type": row.get("display_type") or signal_display_type(row.get("signal_type")),
                "market": row["market"],
                "outcome_name": row.get("outcome_name"),
                "direction": row["direction"],
                "strength_score": row["strength_score"],
                "created_at": row["created_at"],
                "freshness_bucket": row["freshness_bucket"],
                "books_considered": row["books_considered"],
                "opportunity_status": row["opportunity_status"],
                "best_delta": row.get("best_delta"),
                "delta_type": row.get("delta_type"),
            }
        )
    return redacted_rows


async def get_public_teaser_kpis(
    db: AsyncSession,
    *,
    sport_key: str | None = None,
    window_hours: int = 24,
    delay_minutes: int = 15,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    normalized_window_hours = max(1, min(int(window_hours), 72))
    cutoff = now - timedelta(hours=normalized_window_hours)
    delay_cutoff = now - timedelta(minutes=max(0, int(delay_minutes)))

    signal_count_stmt = select(func.count(Signal.id)).where(Signal.created_at >= cutoff)
    if sport_key:
        signal_count_stmt = signal_count_stmt.join(Game, Game.event_id == Signal.event_id).where(
            Game.sport_key == sport_key
        )
    signal_count_stmt = apply_structural_core_query_filters(
        signal_count_stmt,
        signal_model=Signal,
        context="get_public_teaser_kpis",
    )
    signals_in_window = int((await db.execute(signal_count_stmt)).scalar() or 0)

    books_stmt = select(func.count(func.distinct(OddsSnapshot.sportsbook_key))).where(OddsSnapshot.fetched_at >= cutoff)
    if sport_key:
        books_stmt = books_stmt.where(OddsSnapshot.sport_key == sport_key)
    books_tracked_estimate = int((await db.execute(books_stmt)).scalar() or 0)

    window_days = max(1, (normalized_window_hours + 23) // 24)
    opportunities = await get_best_opportunities(
        db,
        days=window_days,
        sport_key=sport_key,
        min_strength=max(1, int(settings.signal_filter_default_min_strength)),
        limit=150,
        include_stale=True,
    )
    window_opportunities = [
        row
        for row in opportunities
        if row.get("created_at") is not None and cutoff <= row["created_at"] <= delay_cutoff
    ]
    sample_size = len(window_opportunities)
    actionable_count = sum(1 for row in window_opportunities if str(row.get("opportunity_status")) == "actionable")
    fresh_count = sum(1 for row in window_opportunities if str(row.get("freshness_bucket")) == "fresh")

    pct_actionable = (actionable_count / sample_size * 100.0) if sample_size else 0.0
    pct_fresh = (fresh_count / sample_size * 100.0) if sample_size else 0.0

    return {
        "signals_in_window": signals_in_window,
        "books_tracked_estimate": books_tracked_estimate,
        "pct_actionable": round(pct_actionable, 1),
        "pct_fresh": round(pct_fresh, 1),
        "updated_at": now,
    }
