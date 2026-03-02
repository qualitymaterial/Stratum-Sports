from __future__ import annotations

import logging
from collections import defaultdict
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_lead_lag_event import CrossMarketLeadLagEvent
from app.models.exchange_market_snapshot import ExchangeMarketSnapshot
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.signal import Signal

logger = logging.getLogger(__name__)


def compute_kalshi_skew_gate(skew: float | None) -> dict[str, Any]:
    """
    Compute Kalshi liquidity skew gates.
    """
    settings = get_settings()

    res = {
        "kalshi_liquidity_skew": skew,
        "kalshi_gate_threshold": settings.kalshi_skew_gate_threshold,
        "kalshi_gate_mode": settings.kalshi_skew_gate_mode,
        "kalshi_skew_bucket": None,
        "kalshi_gate_pass": None,
    }

    if skew is None:
        return res

    bucket = "A: <0.55"
    if skew < 0.55:
        bucket = "A: <0.55"
    elif skew < 0.60:
        bucket = "B: 0.55-0.60"
    elif skew <= 0.65:
        bucket = "C: 0.60-0.65"
    else:
        bucket = "D: >0.65"

    res["kalshi_skew_bucket"] = bucket
    res["kalshi_gate_pass"] = skew >= settings.kalshi_skew_gate_threshold

    return res


async def attach_exchange_liquidity_skew(db: AsyncSession, signals: list[Signal]) -> None:
    """
    Attach exchange microstructure + lead-lag metadata to signal payloads.

    Backward compatibility: if no market snapshot exists for a canonical key,
    exchange_liquidity_skew falls back to the latest ExchangeQuoteEvent.
    """
    if not signals:
        return

    event_ids = list({s.event_id for s in signals})
    align_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.sportsbook_event_id.in_(event_ids)
    )
    alignments = list((await db.execute(align_stmt)).scalars().all())

    if not alignments:
        return

    event_to_cek = {a.sportsbook_event_id: a.canonical_event_key for a in alignments}
    cek_list = list({cek for cek in event_to_cek.values()})

    snapshots_by_cek = await _load_recent_kalshi_snapshots(db, cek_list, per_key_limit=6)
    lead_lag_by_cek = await _load_latest_lead_lag(db, cek_list)
    quote_skew_by_cek = await _load_latest_quote_skew(db, cek_list)

    for signal in signals:
        cek = event_to_cek.get(signal.event_id)
        if not cek:
            continue

        meta = dict(signal.metadata_json or {})

        snapshots = snapshots_by_cek.get(cek, [])
        if snapshots:
            meta.update(_build_market_snapshot_intel(snapshots))

        if "exchange_liquidity_skew" not in meta:
            skew = quote_skew_by_cek.get(cek)
            if skew is not None:
                meta["exchange_liquidity_skew"] = round(skew, 4)

        lead_lag = lead_lag_by_cek.get(cek)
        if lead_lag is not None:
            meta["exchange_lead_source"] = lead_lag.lead_source
            meta["exchange_lead_lag_seconds"] = lead_lag.lag_seconds
            meta["exchange_lead_lag_recorded_at"] = lead_lag.created_at.isoformat()
            meta["exchange_break_timestamp"] = lead_lag.exchange_break_timestamp.isoformat()
            meta["sportsbook_break_timestamp"] = lead_lag.sportsbook_break_timestamp.isoformat()

        signal.metadata_json = meta


async def _load_recent_kalshi_snapshots(
    db: AsyncSession,
    canonical_event_keys: list[str],
    per_key_limit: int,
) -> dict[str, list[ExchangeMarketSnapshot]]:
    if not canonical_event_keys:
        return {}

    ranked = (
        select(
            ExchangeMarketSnapshot.id.label("id"),
            func.row_number()
            .over(
                partition_by=ExchangeMarketSnapshot.canonical_event_key,
                order_by=ExchangeMarketSnapshot.timestamp.desc(),
            )
            .label("rn"),
        )
        .where(
            ExchangeMarketSnapshot.source == "KALSHI",
            ExchangeMarketSnapshot.canonical_event_key.in_(canonical_event_keys),
        )
        .subquery()
    )

    stmt = (
        select(ExchangeMarketSnapshot)
        .join(ranked, ExchangeMarketSnapshot.id == ranked.c.id)
        .where(ranked.c.rn <= per_key_limit)
        .order_by(
            ExchangeMarketSnapshot.canonical_event_key.asc(),
            ExchangeMarketSnapshot.timestamp.desc(),
        )
    )
    rows = list((await db.execute(stmt)).scalars().all())

    grouped: dict[str, list[ExchangeMarketSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[row.canonical_event_key].append(row)
    return grouped


async def _load_latest_lead_lag(
    db: AsyncSession,
    canonical_event_keys: list[str],
) -> dict[str, CrossMarketLeadLagEvent]:
    if not canonical_event_keys:
        return {}

    ranked = (
        select(
            CrossMarketLeadLagEvent.id.label("id"),
            func.row_number()
            .over(
                partition_by=CrossMarketLeadLagEvent.canonical_event_key,
                order_by=CrossMarketLeadLagEvent.created_at.desc(),
            )
            .label("rn"),
        )
        .where(CrossMarketLeadLagEvent.canonical_event_key.in_(canonical_event_keys))
        .subquery()
    )

    stmt = (
        select(CrossMarketLeadLagEvent)
        .join(ranked, CrossMarketLeadLagEvent.id == ranked.c.id)
        .where(ranked.c.rn == 1)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return {row.canonical_event_key: row for row in rows}


async def _load_latest_quote_skew(
    db: AsyncSession,
    canonical_event_keys: list[str],
) -> dict[str, float]:
    if not canonical_event_keys:
        return {}

    stmt = (
        select(ExchangeQuoteEvent)
        .where(
            ExchangeQuoteEvent.source == "KALSHI",
            ExchangeQuoteEvent.canonical_event_key.in_(canonical_event_keys),
        )
        .distinct(ExchangeQuoteEvent.canonical_event_key)
        .order_by(
            ExchangeQuoteEvent.canonical_event_key.asc(),
            ExchangeQuoteEvent.timestamp.desc(),
        )
    )
    rows = list((await db.execute(stmt)).scalars().all())

    skew_by_key: dict[str, float] = {}
    for row in rows:
        p = row.probability
        skew_by_key[row.canonical_event_key] = max(p, 1.0 - p)
    return skew_by_key


def _build_market_snapshot_intel(snapshots_desc: list[ExchangeMarketSnapshot]) -> dict[str, Any]:
    if not snapshots_desc:
        return {}

    ordered = sorted(snapshots_desc, key=lambda s: s.timestamp)
    latest = ordered[-1]
    meta: dict[str, Any] = {}

    yes_mid = _mid_probability(latest.yes_bid_probability, latest.yes_ask_probability)
    if yes_mid is None:
        no_mid = _mid_probability(latest.no_bid_probability, latest.no_ask_probability)
        if no_mid is not None:
            yes_mid = 1.0 - no_mid
    if yes_mid is not None:
        meta["exchange_liquidity_skew"] = round(max(yes_mid, 1.0 - yes_mid), 4)

    spreads = []
    for bid, ask in (
        (latest.yes_bid_probability, latest.yes_ask_probability),
        (latest.no_bid_probability, latest.no_ask_probability),
    ):
        if bid is None or ask is None or ask < bid:
            continue
        spreads.append(ask - bid)
    if spreads:
        avg_spread = sum(spreads) / len(spreads)
        meta["exchange_top_book_spread_bps"] = round(avg_spread * 10_000, 2)

    yes_depth = _depth_total(latest.yes_bid_size, latest.yes_ask_size)
    no_depth = _depth_total(latest.no_bid_size, latest.no_ask_size)
    if yes_depth is not None or no_depth is not None:
        yes_depth = yes_depth or 0
        no_depth = no_depth or 0
        total_depth = yes_depth + no_depth
        if total_depth > 0:
            meta["exchange_depth_imbalance"] = round((yes_depth - no_depth) / total_depth, 4)
            meta["exchange_depth_total_size"] = total_depth

    meta.update(_trade_flow_intel(ordered))
    return meta


def _trade_flow_intel(snapshots_asc: list[ExchangeMarketSnapshot]) -> dict[str, Any]:
    if len(snapshots_asc) < 2:
        return {}

    rate_observations: list[float] = []
    latest_volume_delta: int | None = None
    latest_rate: float | None = None
    latest_window_minutes: float | None = None

    for prev, curr in zip(snapshots_asc, snapshots_asc[1:]):
        dt_seconds = (curr.timestamp - prev.timestamp).total_seconds()
        if dt_seconds <= 0:
            continue
        vol_delta = _non_negative_delta(prev.volume, curr.volume)
        if vol_delta is None:
            continue
        dt_minutes = dt_seconds / 60.0
        rate = vol_delta / dt_minutes
        rate_observations.append(rate)
        latest_volume_delta = vol_delta
        latest_rate = rate
        latest_window_minutes = dt_minutes

    if latest_volume_delta is None or latest_rate is None or latest_window_minutes is None:
        return {}

    res: dict[str, Any] = {
        "exchange_trade_flow_volume_delta": latest_volume_delta,
        "exchange_trade_flow_rate_per_min": round(latest_rate, 4),
        "exchange_trade_flow_window_minutes": round(latest_window_minutes, 3),
    }

    latest = snapshots_asc[-1]
    prev = snapshots_asc[-2]
    oi_delta = _delta(prev.open_interest, latest.open_interest)
    if oi_delta is not None:
        res["exchange_trade_flow_open_interest_delta"] = oi_delta

    if len(rate_observations) > 1:
        baseline = float(median(rate_observations[:-1]))
        res["exchange_trade_flow_baseline_rate_per_min"] = round(baseline, 4)
        if baseline > 0:
            res["exchange_trade_flow_burst_score"] = round(latest_rate / baseline, 4)

    return res


def _mid_probability(bid: float | None, ask: float | None) -> float | None:
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    return None


def _depth_total(*values: int | None) -> int | None:
    parsed = [v for v in values if v is not None]
    if not parsed:
        return None
    return int(sum(parsed))


def _non_negative_delta(old: int | None, new: int | None) -> int | None:
    if old is None or new is None:
        return None
    return max(0, int(new - old))


def _delta(old: int | None, new: int | None) -> int | None:
    if old is None or new is None:
        return None
    return int(new - old)
