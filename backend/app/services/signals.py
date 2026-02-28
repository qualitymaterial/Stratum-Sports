import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean, median as stats_median
from typing import Iterable

from redis.asyncio import Redis
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.public_signal_surface import signal_display_type
from app.services.time_bucket import compute_time_bucket

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class BookMove:
    sportsbook_key: str
    from_value: float
    to_value: float
    direction: str
    velocity_minutes: float


@dataclass
class DislocationCandidate:
    event_id: str
    strength_score: int
    dedupe_key: str
    signal: Signal


@dataclass
class SteamBookWindow:
    sportsbook_key: str
    earliest_line: float
    latest_line: float
    move: float


@dataclass
class SteamCandidate:
    event_id: str
    strength_score: int
    dedupe_key: str
    signal: Signal


def crosses_key_number(from_value: float, to_value: float, key_numbers: Iterable[float]) -> bool:
    from_abs = abs(from_value)
    to_abs = abs(to_value)
    for key in key_numbers:
        if (from_abs < key <= to_abs) or (to_abs < key <= from_abs):
            return True
    return False


def should_trigger_spread_move(
    from_value: float,
    to_value: float,
    key_numbers: Iterable[float],
) -> tuple[bool, str, bool, float]:
    magnitude = abs(to_value - from_value)
    key_cross = crosses_key_number(from_value, to_value, key_numbers)
    triggered = magnitude >= 0.5 or key_cross
    signal_type = "KEY_CROSS" if key_cross else "MOVE"
    return triggered, signal_type, key_cross, magnitude


def should_trigger_total_move(from_value: float, to_value: float) -> tuple[bool, float]:
    magnitude = abs(to_value - from_value)
    return magnitude >= 1.0, magnitude


def compute_strength_score(
    *,
    magnitude: float,
    velocity_minutes: float,
    window_minutes: int,
    books_affected: int,
    minutes_to_tip: float | None = None,
) -> tuple[int, dict]:
    if minutes_to_tip is None:
        magnitude_component = min(50.0, abs(magnitude) * 20.0)

        capped_velocity = min(max(velocity_minutes, 0.01), float(window_minutes))
        speed_component = min(
            30.0,
            ((float(window_minutes) - capped_velocity) / float(window_minutes)) * 30.0,
        )
        books_component = min(20.0, float(max(books_affected, 1)) * 4.0)

        score = int(max(1, min(100, round(magnitude_component + speed_component + books_component))))
        return (
            score,
            {
                "magnitude_component": round(magnitude_component, 2),
                "speed_component": round(speed_component, 2),
                "books_component": round(books_component, 2),
            },
        )

    magnitude_component = min(40.0, abs(magnitude) * 16.0)

    capped_velocity = min(max(velocity_minutes, 0.01), float(window_minutes))
    speed_component = min(
        25.0,
        ((float(window_minutes) - capped_velocity) / float(window_minutes)) * 25.0,
    )
    books_component = min(15.0, float(max(books_affected, 1)) * 3.0)
    timing_component = _timing_component(minutes_to_tip)

    score = int(
        max(
            1,
            min(
                100,
                round(magnitude_component + speed_component + books_component + timing_component),
            ),
        )
    )
    return (
        score,
        {
            "magnitude_component": round(magnitude_component, 2),
            "speed_component": round(speed_component, 2),
            "books_component": round(books_component, 2),
            "timing_component": round(timing_component, 2),
        },
    )


def _timing_component(minutes_to_tip: float) -> float:
    if minutes_to_tip >= 0:
        pre_tip_minutes = min(minutes_to_tip, 240.0)
        return 4.0 + (pre_tip_minutes / 240.0) * 16.0

    post_tip_minutes = min(abs(minutes_to_tip), 180.0)
    return max(-8.0, 4.0 - (post_tip_minutes / 15.0))


def american_to_implied_prob(price: int | float | None) -> float | None:
    if price is None:
        return None
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None

    if value == 0:
        return None
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def compute_strength_dislocation(
    delta: float,
    dispersion: float | None,
    books_count: int,
    market: str,
) -> int:
    baseline = 1.0
    if market == "totals":
        baseline = max(settings.dislocation_total_line_delta, 0.0001)
    elif market == "h2h":
        baseline = max(settings.dislocation_ml_implied_prob_delta, 0.0001)
    else:
        baseline = max(settings.dislocation_spread_line_delta, 0.0001)

    delta_ratio = max(delta, 0.0) / baseline
    delta_component = min(55.0, delta_ratio * 20.0)

    if dispersion is None:
        dispersion_component = 5.0
    else:
        dispersion_component = max(0.0, min(20.0, 20.0 / (1.0 + abs(float(dispersion)) * 2.5)))

    books_component = min(15.0, max(0.0, float(books_count - 4) * 2.0))
    score = int(max(1, min(100, round(8.0 + delta_component + dispersion_component + books_component))))
    return score


def compute_strength_steam(
    total_move: float,
    speed: float,
    books_count: int,
    market: str,
) -> int:
    threshold = settings.steam_min_move_spread if market == "spreads" else settings.steam_min_move_total
    threshold = max(float(threshold), 0.0001)
    window = max(1.0, float(settings.steam_window_minutes))

    move_ratio = abs(total_move) / threshold
    move_component = min(40.0, move_ratio * 16.0)

    books_above_min = max(0, books_count - settings.steam_min_books + 1)
    books_component = min(22.0, float(books_above_min) * 5.5)

    baseline_speed = threshold / window
    speed_ratio = speed / max(baseline_speed, 0.0001)
    speed_component = min(18.0, speed_ratio * 6.0)

    score = int(max(1, min(100, round(8.0 + move_component + books_component + speed_component))))
    return score


async def _dedupe_signal(redis: Redis | None, key: str, ttl_seconds: int) -> bool:
    if redis is None:
        return False
    try:
        was_set = await redis.set(key, "1", ex=ttl_seconds, nx=True)
        return not bool(was_set)
    except Exception:
        logger.exception("Signal redis dedupe failed")
        return False


def _direction(from_value: float, to_value: float) -> str:
    if to_value > from_value:
        return "UP"
    if to_value < from_value:
        return "DOWN"
    return "FLAT"


async def _commence_time_by_event(
    db: AsyncSession,
    event_ids: list[str],
) -> dict[str, datetime]:
    if not event_ids:
        return {}
    stmt = select(Game.event_id, Game.commence_time).where(Game.event_id.in_(event_ids))
    rows = (await db.execute(stmt)).all()
    return {event_id: commence_time for event_id, commence_time in rows}


def _minutes_to_tip(
    *,
    event_id: str,
    commence_time_map: dict[str, datetime] | None,
    now: datetime,
) -> float | None:
    if not commence_time_map:
        return None
    commence_time = commence_time_map.get(event_id)
    if commence_time is None:
        return None
    commence_utc = commence_time if commence_time.tzinfo is not None else commence_time.replace(tzinfo=UTC)
    return (commence_utc - now).total_seconds() / 60.0


def serialize_signal(signal: Signal, *, pro_user: bool) -> dict:
    metadata = dict(signal.metadata_json or {})
    freshness_seconds = max(0, int((datetime.now(UTC) - signal.created_at).total_seconds()))
    if freshness_seconds <= 5 * 60:
        freshness_bucket = "fresh"
    elif freshness_seconds <= 10 * 60:
        freshness_bucket = "aging"
    else:
        freshness_bucket = "stale"

    metadata["books_count"] = signal.books_affected
    metadata["freshness_seconds"] = freshness_seconds
    metadata["freshness_bucket"] = freshness_bucket

    if not pro_user:
        books = metadata.get("books")
        books_involved = metadata.get("books_involved")
        metadata = {k: v for k, v in metadata.items() if k not in {"books", "books_involved", "components"}}
        if isinstance(books, list):
            metadata["books"] = books[:3]
        elif isinstance(books_involved, list):
            metadata["books"] = books_involved[:3]

    return {
        "id": signal.id,
        "event_id": signal.event_id,
        "market": signal.market,
        "signal_type": signal.signal_type,
        "display_type": signal_display_type(signal.signal_type),
        "direction": signal.direction,
        "from_value": signal.from_value,
        "to_value": signal.to_value,
        "from_price": signal.from_price,
        "to_price": signal.to_price,
        "window_minutes": signal.window_minutes,
        "books_affected": signal.books_affected,
        "velocity_minutes": signal.velocity_minutes if pro_user else None,
        "time_bucket": signal.time_bucket,
        "freshness_seconds": freshness_seconds,
        "freshness_bucket": freshness_bucket,
        "strength_score": signal.strength_score,
        "created_at": signal.created_at,
        "metadata": metadata,
    }


def summarize_signals_by_type(signals: list[Signal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        counts[signal.signal_type] = counts.get(signal.signal_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


async def _detect_line_move_signals(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
    market: str,
    window_minutes: int,
    commence_time_map: dict[str, datetime] | None = None,
) -> list[Signal]:
    now = datetime.now(UTC)
    start_ts = now - timedelta(minutes=window_minutes)

    # Single query across all event_ids — was one query per event before
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(event_ids),
            OddsSnapshot.market == market,
            OddsSnapshot.fetched_at >= start_ts,
        )
        .order_by(OddsSnapshot.event_id, OddsSnapshot.outcome_name, OddsSnapshot.fetched_at)
    )
    snapshots = (await db.execute(stmt)).scalars().all()
    if not snapshots:
        return []

    # Group by (event_id, outcome_name) across all events in one pass
    grouped: dict[tuple[str, str], list[OddsSnapshot]] = defaultdict(list)
    for snap in snapshots:
        if snap.line is None:
            continue
        grouped[(snap.event_id, snap.outcome_name)].append(snap)

    created: list[Signal] = []

    for (event_id, outcome_name), snaps in grouped.items():
        if len(snaps) < 2:
            continue

        from_snap = snaps[0]
        to_snap = snaps[-1]

        from_value = float(from_snap.line)
        to_value = float(to_snap.line)
        triggered = False
        magnitude = abs(to_value - from_value)
        velocity_minutes = max(
            0.1,
            (to_snap.fetched_at - from_snap.fetched_at).total_seconds() / 60.0,
        )
        direction = _direction(from_value, to_value)
        books = sorted({snap.sportsbook_key for snap in snaps})

        if market == "spreads":
            triggered, signal_type, crosses, magnitude = should_trigger_spread_move(
                from_value,
                to_value,
                settings.nba_key_numbers_list,
            )
        else:
            triggered, magnitude = should_trigger_total_move(from_value, to_value)
            signal_type = "MOVE"
            crosses = False

        if not triggered:
            continue

        dedupe_key = (
            f"signal:{event_id}:{market}:{signal_type}:{direction}:"
            f"{outcome_name}:{round(from_value, 2)}:{round(to_value, 2)}"
        )
        if await _dedupe_signal(redis, dedupe_key, ttl_seconds=window_minutes * 60):
            continue

        minutes_to_tip: float | None = None
        time_bucket = "UNKNOWN"
        try:
            minutes_to_tip = _minutes_to_tip(
                event_id=event_id,
                commence_time_map=commence_time_map,
                now=now,
            )
            time_bucket = compute_time_bucket(minutes_to_tip)
        except Exception:
            logger.warning(
                "Signal time bucket computation failed",
                extra={"event_id": event_id, "market": market, "signal_type": signal_type},
            )

        strength, components = compute_strength_score(
            magnitude=magnitude,
            velocity_minutes=velocity_minutes,
            window_minutes=window_minutes,
            books_affected=len(books),
            minutes_to_tip=minutes_to_tip,
        )

        signal = Signal(
            event_id=event_id,
            market=market,
            signal_type=signal_type,
            direction=direction,
            from_value=from_value,
            to_value=to_value,
            from_price=from_snap.price,
            to_price=to_snap.price,
            window_minutes=window_minutes,
            books_affected=len(books),
            velocity_minutes=velocity_minutes,
            time_bucket=time_bucket,
            strength_score=strength,
            metadata_json={
                "outcome_name": outcome_name,
                "magnitude": round(magnitude, 3),
                "key_cross": crosses,
                "books": books,
                "minutes_to_tip": round(minutes_to_tip, 2) if minutes_to_tip is not None else None,
                "components": components,
            },
        )
        db.add(signal)
        created.append(signal)

    return created


async def _detect_live_shock_signals(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
    commence_time_map: dict[str, datetime] | None = None,
) -> list[Signal]:
    now = datetime.now(UTC)
    # Check if the event is actually live (started in the last 4 hours or starting in <5 mins)
    live_event_ids = []
    for eid in event_ids:
        mins_to_tip = _minutes_to_tip(event_id=eid, commence_time_map=commence_time_map, now=now)
        if mins_to_tip is not None and -240 <= mins_to_tip <= 5:
            live_event_ids.append(eid)
            
    if not live_event_ids:
        return []

    window_minutes = 5
    start_ts = now - timedelta(minutes=window_minutes)

    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(live_event_ids),
            OddsSnapshot.fetched_at >= start_ts,
        )
        .order_by(OddsSnapshot.event_id, OddsSnapshot.market, OddsSnapshot.outcome_name, OddsSnapshot.fetched_at)
    )
    snapshots = (await db.execute(stmt)).scalars().all()
    if not snapshots:
        return []

    grouped: dict[tuple[str, str, str], list[OddsSnapshot]] = defaultdict(list)
    for snap in snapshots:
        grouped[(snap.event_id, snap.market, snap.outcome_name)].append(snap)

    created: list[Signal] = []
    for (event_id, market, outcome_name), snaps in grouped.items():
        if len(snaps) < 2:
            continue

        from_snap = snaps[0]
        to_snap = snaps[-1]
        
        from_value = float(from_snap.line) if from_snap.line is not None else float(from_snap.price)
        to_value = float(to_snap.line) if to_snap.line is not None else float(to_snap.price)
        magnitude = abs(to_value - from_value)
        direction = _direction(from_value, to_value)
        
        triggered = False
        if market == "spreads" and magnitude >= 4.5:
             triggered = True
        elif market == "totals" and magnitude >= 6.5:
             triggered = True
        elif market == "h2h":
             prob_from = american_to_implied_prob(from_snap.price)
             prob_to = american_to_implied_prob(to_snap.price)
             if prob_from is not None and prob_to is not None and abs(prob_to - prob_from) >= 0.15:
                 triggered = True

        if not triggered:
            continue
            
        dedupe_key = (
            f"signal:{event_id}:{market}:LIVE_SHOCK:{direction}:"
            f"{outcome_name}:{round(from_value, 2)}:{round(to_value, 2)}"
        )
        if await _dedupe_signal(redis, dedupe_key, ttl_seconds=window_minutes * 60):
            continue

        books = sorted({snap.sportsbook_key for snap in snaps})
        mins_to_tip = _minutes_to_tip(event_id=event_id, commence_time_map=commence_time_map, now=now)
        time_bucket = compute_time_bucket(mins_to_tip)
        
        # Override strength statically for shocks
        strength = 100 

        signal = Signal(
            event_id=event_id,
            market=market,
            signal_type="LIVE_SHOCK",
            direction=direction,
            from_value=from_value,
            to_value=to_value,
            from_price=from_snap.price,
            to_price=to_snap.price,
            window_minutes=window_minutes,
            books_affected=len(books),
            velocity_minutes=max(0.1, (to_snap.fetched_at - from_snap.fetched_at).total_seconds() / 60.0),
            time_bucket=time_bucket,
            strength_score=strength,
            metadata_json={
                "outcome_name": outcome_name,
                "magnitude": round(magnitude, 3),
                "books": books,
                "minutes_to_tip": round(mins_to_tip, 2) if mins_to_tip is not None else None,
            },
        )
        db.add(signal)
        created.append(signal)

    return created

async def _detect_multibook_sync_signals(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
    commence_time_map: dict[str, datetime] | None = None,
) -> list[Signal]:
    window_minutes = 5
    now = datetime.now(UTC)
    start_ts = now - timedelta(minutes=window_minutes)

    # Single query across all event_ids — was one query per event before
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(event_ids),
            OddsSnapshot.fetched_at >= start_ts,
        )
        .order_by(
            OddsSnapshot.event_id,
            OddsSnapshot.market,
            OddsSnapshot.outcome_name,
            OddsSnapshot.sportsbook_key,
            OddsSnapshot.fetched_at,
        )
    )
    snapshots = (await db.execute(stmt)).scalars().all()
    if not snapshots:
        return []

    by_group: dict[tuple[str, str, str, str], list[OddsSnapshot]] = defaultdict(list)
    for snap in snapshots:
        key = (snap.event_id, snap.market, snap.outcome_name, snap.sportsbook_key)
        by_group[key].append(snap)

    aggregate: dict[tuple[str, str, str, str], list[BookMove]] = defaultdict(list)
    for (event_id, market, outcome_name, sportsbook_key), snaps in by_group.items():
        if len(snaps) < 2:
            continue

        from_snap = snaps[0]
        to_snap = snaps[-1]

        from_value = float(from_snap.line) if from_snap.line is not None else float(from_snap.price)
        to_value = float(to_snap.line) if to_snap.line is not None else float(to_snap.price)
        if from_value == to_value:
            continue

        aggregate[(event_id, market, outcome_name, _direction(from_value, to_value))].append(
            BookMove(
                sportsbook_key=sportsbook_key,
                from_value=from_value,
                to_value=to_value,
                direction=_direction(from_value, to_value),
                velocity_minutes=max(
                    0.1,
                    (to_snap.fetched_at - from_snap.fetched_at).total_seconds() / 60.0,
                ),
            )
        )

    created: list[Signal] = []

    for (event_id, market, outcome_name, direction), moves in aggregate.items():
        if len(moves) < 3:
            continue

        avg_from = mean([m.from_value for m in moves])
        avg_to = mean([m.to_value for m in moves])
        magnitude = abs(avg_to - avg_from)
        velocity = mean([m.velocity_minutes for m in moves])

        dedupe_key = (
            f"signal:{event_id}:{market}:MULTIBOOK_SYNC:{direction}:"
            f"{outcome_name}:{round(avg_to, 2)}:{len(moves)}"
        )
        if await _dedupe_signal(redis, dedupe_key, ttl_seconds=window_minutes * 60):
            continue

        books = sorted({m.sportsbook_key for m in moves})
        minutes_to_tip: float | None = None
        time_bucket = "UNKNOWN"
        try:
            minutes_to_tip = _minutes_to_tip(
                event_id=event_id,
                commence_time_map=commence_time_map,
                now=now,
            )
            time_bucket = compute_time_bucket(minutes_to_tip)
        except Exception:
            logger.warning(
                "Signal time bucket computation failed",
                extra={"event_id": event_id, "market": market, "signal_type": "MULTIBOOK_SYNC"},
            )

        strength, components = compute_strength_score(
            magnitude=magnitude,
            velocity_minutes=velocity,
            window_minutes=window_minutes,
            books_affected=len(moves),
            minutes_to_tip=minutes_to_tip,
        )
        signal = Signal(
            event_id=event_id,
            market=market,
            signal_type="MULTIBOOK_SYNC",
            direction=direction,
            from_value=float(avg_from),
            to_value=float(avg_to),
            from_price=int(round(avg_from)) if market == "h2h" else None,
            to_price=int(round(avg_to)) if market == "h2h" else None,
            window_minutes=window_minutes,
            books_affected=len(moves),
            velocity_minutes=float(velocity),
            time_bucket=time_bucket,
            strength_score=strength,
            metadata_json={
                "outcome_name": outcome_name,
                "books": books,
                "magnitude": round(magnitude, 3),
                "minutes_to_tip": round(minutes_to_tip, 2) if minutes_to_tip is not None else None,
                "components": components,
            },
        )
        db.add(signal)
        created.append(signal)

    return created


async def _latest_consensus_rows_for_events(
    db: AsyncSession,
    event_ids: list[str],
    markets: list[str],
    lookback_minutes: int,
    min_books: int,
) -> list[MarketConsensusSnapshot]:
    cutoff = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    latest_subquery = (
        select(
            MarketConsensusSnapshot.event_id.label("event_id"),
            MarketConsensusSnapshot.market.label("market"),
            MarketConsensusSnapshot.outcome_name.label("outcome_name"),
            func.max(MarketConsensusSnapshot.fetched_at).label("max_fetched_at"),
        )
        .where(
            MarketConsensusSnapshot.event_id.in_(event_ids),
            MarketConsensusSnapshot.market.in_(markets),
            MarketConsensusSnapshot.fetched_at >= cutoff,
            MarketConsensusSnapshot.books_count >= min_books,
        )
        .group_by(
            MarketConsensusSnapshot.event_id,
            MarketConsensusSnapshot.market,
            MarketConsensusSnapshot.outcome_name,
        )
        .subquery()
    )

    stmt = (
        select(MarketConsensusSnapshot)
        .join(
            latest_subquery,
            and_(
                MarketConsensusSnapshot.event_id == latest_subquery.c.event_id,
                MarketConsensusSnapshot.market == latest_subquery.c.market,
                MarketConsensusSnapshot.outcome_name == latest_subquery.c.outcome_name,
                MarketConsensusSnapshot.fetched_at == latest_subquery.c.max_fetched_at,
            ),
        )
        .order_by(
            MarketConsensusSnapshot.event_id.asc(),
            MarketConsensusSnapshot.market.asc(),
            MarketConsensusSnapshot.outcome_name.asc(),
        )
    )
    return (await db.execute(stmt)).scalars().all()


async def _latest_snapshot_by_book_for_events(
    db: AsyncSession,
    event_ids: list[str],
    markets: list[str],
    lookback_minutes: int,
) -> dict[tuple[str, str, str], list[OddsSnapshot]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(event_ids),
            OddsSnapshot.market.in_(markets),
            OddsSnapshot.fetched_at >= cutoff,
        )
        .order_by(
            OddsSnapshot.event_id.asc(),
            OddsSnapshot.market.asc(),
            OddsSnapshot.outcome_name.asc(),
            OddsSnapshot.sportsbook_key.asc(),
            OddsSnapshot.fetched_at.desc(),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()

    latest_by_key: dict[tuple[str, str, str, str], OddsSnapshot] = {}
    for row in rows:
        key = (row.event_id, row.market, row.outcome_name, row.sportsbook_key)
        if key in latest_by_key:
            continue
        latest_by_key[key] = row

    by_event_market_outcome: dict[tuple[str, str, str], list[OddsSnapshot]] = defaultdict(list)
    for row in latest_by_key.values():
        by_event_market_outcome[(row.event_id, row.market, row.outcome_name)].append(row)

    return by_event_market_outcome


async def detect_dislocations(
    event_ids: list[str],
    db: AsyncSession,
    redis: Redis | None = None,
    commence_time_map: dict[str, datetime] | None = None,
) -> list[Signal]:
    if not settings.dislocation_enabled or not event_ids:
        return []

    markets = [m for m in settings.consensus_markets_list if m in {"spreads", "totals", "h2h"}]
    if not markets:
        return []

    min_books = max(settings.dislocation_min_books, settings.consensus_min_books)
    lookback_minutes = max(1, settings.dislocation_lookback_minutes)
    now = datetime.now(UTC)
    consensus_rows = await _latest_consensus_rows_for_events(
        db,
        event_ids=event_ids,
        markets=markets,
        lookback_minutes=lookback_minutes,
        min_books=min_books,
    )
    if not consensus_rows:
        return []

    latest_snapshots = await _latest_snapshot_by_book_for_events(
        db,
        event_ids=event_ids,
        markets=markets,
        lookback_minutes=lookback_minutes,
    )
    if not latest_snapshots:
        return []

    candidate_by_event: dict[str, list[DislocationCandidate]] = defaultdict(list)
    for consensus in consensus_rows:
        key = (consensus.event_id, consensus.market, consensus.outcome_name)
        for snapshot in latest_snapshots.get(key, []):
            delta = 0.0
            delta_type = "line"
            from_value = 0.0
            to_value = 0.0
            from_price: int | None = None
            to_price: int | None = None

            if consensus.market in {"spreads", "totals"}:
                if consensus.consensus_line is None or snapshot.line is None:
                    continue
                threshold = (
                    settings.dislocation_spread_line_delta
                    if consensus.market == "spreads"
                    else settings.dislocation_total_line_delta
                )
                from_value = float(consensus.consensus_line)
                to_value = float(snapshot.line)
                delta = to_value - from_value
                if abs(delta) < threshold:
                    continue
                from_price = int(round(consensus.consensus_price)) if consensus.consensus_price is not None else None
                to_price = int(snapshot.price)
            else:
                if consensus.consensus_price is None:
                    continue
                consensus_prob = american_to_implied_prob(consensus.consensus_price)
                book_prob = american_to_implied_prob(snapshot.price)
                if consensus_prob is None or book_prob is None:
                    continue
                delta_type = "implied_prob"
                from_value = float(consensus_prob)
                to_value = float(book_prob)
                delta = to_value - from_value
                if abs(delta) < settings.dislocation_ml_implied_prob_delta:
                    continue
                from_price = int(round(consensus.consensus_price))
                to_price = int(snapshot.price)

            strength = compute_strength_dislocation(
                delta=abs(delta),
                dispersion=consensus.dispersion,
                books_count=consensus.books_count,
                market=consensus.market,
            )
            direction = _direction(from_value, to_value)
            minutes_to_tip: float | None = None
            time_bucket = "UNKNOWN"
            try:
                minutes_to_tip = _minutes_to_tip(
                    event_id=consensus.event_id,
                    commence_time_map=commence_time_map,
                    now=now,
                )
                time_bucket = compute_time_bucket(minutes_to_tip)
            except Exception:
                logger.warning(
                    "Signal time bucket computation failed",
                    extra={"event_id": consensus.event_id, "market": consensus.market, "signal_type": "DISLOCATION"},
                )
            dedupe_key = (
                f"signal:dislocation:{consensus.event_id}:{consensus.market}:"
                f"{consensus.outcome_name}:{snapshot.sportsbook_key}"
            )
            signal = Signal(
                event_id=consensus.event_id,
                market=consensus.market,
                signal_type="DISLOCATION",
                direction=direction,
                from_value=from_value,
                to_value=to_value,
                from_price=from_price,
                to_price=to_price,
                window_minutes=lookback_minutes,
                books_affected=1,
                velocity_minutes=0.1,
                time_bucket=time_bucket,
                strength_score=strength,
                metadata_json={
                    "book_key": snapshot.sportsbook_key,
                    "market": consensus.market,
                    "outcome_name": consensus.outcome_name,
                    "book_line": float(snapshot.line) if snapshot.line is not None else None,
                    "book_price": float(snapshot.price),
                    "consensus_line": float(consensus.consensus_line) if consensus.consensus_line is not None else None,
                    "consensus_price": float(consensus.consensus_price)
                    if consensus.consensus_price is not None
                    else None,
                    "dispersion": float(consensus.dispersion) if consensus.dispersion is not None else None,
                    "books_count": int(consensus.books_count),
                    "delta": float(round(delta, 6)),
                    "delta_type": delta_type,
                    "lookback_minutes": lookback_minutes,
                    "minutes_to_tip": round(minutes_to_tip, 2) if minutes_to_tip is not None else None,
                },
            )
            candidate_by_event[consensus.event_id].append(
                DislocationCandidate(
                    event_id=consensus.event_id,
                    strength_score=strength,
                    dedupe_key=dedupe_key,
                    signal=signal,
                )
            )

    if not candidate_by_event:
        return []

    created: list[Signal] = []
    max_per_event = max(1, settings.dislocation_max_signals_per_event)
    for event_id, candidates in candidate_by_event.items():
        ranked = sorted(
            candidates,
            key=lambda c: (
                c.strength_score,
                abs(float(c.signal.metadata_json.get("delta", 0.0))),
            ),
            reverse=True,
        )
        for candidate in ranked[:max_per_event]:
            if await _dedupe_signal(redis, candidate.dedupe_key, settings.dislocation_cooldown_seconds):
                continue
            db.add(candidate.signal)
            created.append(candidate.signal)

    if created:
        logger.info(
            "Dislocation detection completed",
            extra={
                "dislocation_signals_created": len(created),
                "dislocation_events_scanned": len(candidate_by_event),
            },
        )

    return created


def _steam_market_threshold(market: str) -> float:
    if market == "spreads":
        return max(0.0, float(settings.steam_min_move_spread))
    if market == "totals":
        return max(0.0, float(settings.steam_min_move_total))
    return 0.0


def _steam_min_per_book_move(market: str) -> float:
    # Conservative micro-noise filter before synchronization checks.
    return max(0.05, _steam_market_threshold(market) * 0.4)


async def detect_steam_v2(
    event_ids: list[str],
    db: AsyncSession,
    redis: Redis | None = None,
    commence_time_map: dict[str, datetime] | None = None,
) -> list[Signal]:
    if not settings.steam_enabled or not event_ids:
        return []

    window_minutes = max(1, settings.steam_window_minutes)
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=window_minutes)
    markets = ["spreads", "totals"]

    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(event_ids),
            OddsSnapshot.market.in_(markets),
            OddsSnapshot.line.is_not(None),
            OddsSnapshot.fetched_at >= cutoff,
        )
        .order_by(
            OddsSnapshot.event_id.asc(),
            OddsSnapshot.market.asc(),
            OddsSnapshot.outcome_name.asc(),
            OddsSnapshot.sportsbook_key.asc(),
            OddsSnapshot.fetched_at.asc(),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    by_book: dict[tuple[str, str, str, str], list[OddsSnapshot]] = defaultdict(list)
    for row in rows:
        by_book[(row.event_id, row.market, row.outcome_name, row.sportsbook_key)].append(row)

    by_direction: dict[tuple[str, str, str, str], list[SteamBookWindow]] = defaultdict(list)
    for (event_id, market, outcome_name, sportsbook_key), snapshots in by_book.items():
        if len(snapshots) < 2:
            continue

        earliest = snapshots[0]
        latest = snapshots[-1]
        if earliest.line is None or latest.line is None:
            continue

        earliest_line = float(earliest.line)
        latest_line = float(latest.line)
        move = latest_line - earliest_line
        if abs(move) < _steam_min_per_book_move(market):
            continue

        direction = _direction(earliest_line, latest_line)
        if direction not in {"UP", "DOWN"}:
            continue

        by_direction[(event_id, market, outcome_name, direction)].append(
            SteamBookWindow(
                sportsbook_key=sportsbook_key,
                earliest_line=earliest_line,
                latest_line=latest_line,
                move=move,
            )
        )

    if not by_direction:
        return []

    candidates_by_event: dict[str, list[SteamCandidate]] = defaultdict(list)
    for (event_id, market, outcome_name, direction), moves in by_direction.items():
        if len(moves) < settings.steam_min_books:
            continue

        start_line = float(stats_median([m.earliest_line for m in moves]))
        end_line = float(stats_median([m.latest_line for m in moves]))
        total_move = end_line - start_line
        threshold = _steam_market_threshold(market)
        if abs(total_move) < threshold:
            continue

        avg_move = float(mean([m.move for m in moves]))
        speed = abs(total_move) / float(window_minutes)
        books_involved = sorted({m.sportsbook_key for m in moves})
        direction_lower = "up" if direction == "UP" else "down"
        strength = compute_strength_steam(
            total_move=total_move,
            speed=speed,
            books_count=len(books_involved),
            market=market,
        )
        dedupe_key = f"signal:steam:{event_id}:{market}:{outcome_name}:{direction_lower}"
        minutes_to_tip: float | None = None
        time_bucket = "UNKNOWN"
        try:
            minutes_to_tip = _minutes_to_tip(
                event_id=event_id,
                commence_time_map=commence_time_map,
                now=now,
            )
            time_bucket = compute_time_bucket(minutes_to_tip)
        except Exception:
            logger.warning(
                "Signal time bucket computation failed",
                extra={"event_id": event_id, "market": market, "signal_type": "STEAM"},
            )

        signal = Signal(
            event_id=event_id,
            market=market,
            signal_type="STEAM",
            direction=direction,
            from_value=start_line,
            to_value=end_line,
            from_price=None,
            to_price=None,
            window_minutes=window_minutes,
            books_affected=len(books_involved),
            velocity_minutes=float(window_minutes),
            time_bucket=time_bucket,
            strength_score=strength,
            metadata_json={
                "market": market,
                "outcome_name": outcome_name,
                "direction": direction_lower,
                "books_involved": books_involved,
                "window_minutes": window_minutes,
                "total_move": round(total_move, 6),
                "avg_move": round(avg_move, 6),
                "start_line": round(start_line, 6),
                "end_line": round(end_line, 6),
                "speed": round(speed, 6),
                "minutes_to_tip": round(minutes_to_tip, 2) if minutes_to_tip is not None else None,
            },
        )
        candidates_by_event[event_id].append(
            SteamCandidate(
                event_id=event_id,
                strength_score=strength,
                dedupe_key=dedupe_key,
                signal=signal,
            )
        )

    if not candidates_by_event:
        return []

    created: list[Signal] = []
    per_event_cap = max(1, settings.steam_max_signals_per_event)
    for event_id, event_candidates in candidates_by_event.items():
        ranked = sorted(
            event_candidates,
            key=lambda c: (
                c.strength_score,
                abs(float(c.signal.metadata_json.get("total_move", 0.0))),
                c.signal.books_affected,
            ),
            reverse=True,
        )
        for candidate in ranked[:per_event_cap]:
            if await _dedupe_signal(redis, candidate.dedupe_key, settings.steam_cooldown_seconds):
                continue
            db.add(candidate.signal)
            created.append(candidate.signal)

    if created:
        logger.info(
            "Steam v2 detection completed",
            extra={"steam_signals_created": len(created), "steam_events_scanned": len(candidates_by_event)},
        )

    return created


# ---------------------------------------------------------------------------
# EXCHANGE_DIVERGENCE — cross-market divergence promoted to user-facing signal
# ---------------------------------------------------------------------------


def compute_strength_exchange_divergence(
    *,
    divergence_type: str,
    lag_seconds: int | None,
    exchange_probability: float | None,
) -> int:
    """Score an exchange divergence event (1-100)."""
    type_component = {"OPPOSED": 40.0, "EXCHANGE_LEADS": 28.0, "SPORTSBOOK_LEADS": 22.0}.get(divergence_type, 15.0)

    if lag_seconds is None:
        lag_component = 15.0
    elif lag_seconds <= 30:
        lag_component = 30.0
    elif lag_seconds <= 120:
        lag_component = 22.0
    elif lag_seconds <= 300:
        lag_component = 14.0
    else:
        lag_component = 6.0

    if exchange_probability is not None:
        prob_distance = abs(exchange_probability - 0.5)
        prob_component = min(30.0, prob_distance * 60.0)
    else:
        prob_component = 10.0

    return max(1, min(100, int(round(type_component + lag_component + prob_component))))


async def detect_exchange_divergence_signals(
    event_ids: list[str],
    db: AsyncSession,
    redis: Redis | None = None,
) -> list[Signal]:
    """Promote actionable CrossMarketDivergenceEvent rows into user-facing Signals."""
    if not settings.exchange_divergence_signal_enabled or not event_ids:
        return []

    from app.models.canonical_event_alignment import CanonicalEventAlignment
    from app.models.cross_market_divergence_event import CrossMarketDivergenceEvent

    # Load alignments for these sportsbook events
    alignment_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.sportsbook_event_id.in_(event_ids)
    )
    alignments = list((await db.execute(alignment_stmt)).scalars().all())
    if not alignments:
        return []

    cek_to_alignment = {a.canonical_event_key: a for a in alignments}
    cek_list = list(cek_to_alignment.keys())

    lookback = max(1, settings.exchange_divergence_lookback_minutes)
    cutoff = datetime.now(UTC) - timedelta(minutes=lookback)
    actionable_types = {"EXCHANGE_LEADS", "SPORTSBOOK_LEADS", "OPPOSED"}

    div_stmt = (
        select(CrossMarketDivergenceEvent)
        .where(
            CrossMarketDivergenceEvent.canonical_event_key.in_(cek_list),
            CrossMarketDivergenceEvent.divergence_type.in_(actionable_types),
            CrossMarketDivergenceEvent.created_at >= cutoff,
        )
        .order_by(desc(CrossMarketDivergenceEvent.created_at))
    )
    divergence_rows = list((await db.execute(div_stmt)).scalars().all())
    if not divergence_rows:
        return []

    # Build commence_time_map for time_bucket
    commence_time_map = await _commence_time_by_event(db, event_ids)
    now = datetime.now(UTC)

    candidate_by_event: dict[str, list[DislocationCandidate]] = defaultdict(list)
    for div_event in divergence_rows:
        alignment = cek_to_alignment.get(div_event.canonical_event_key)
        if alignment is None:
            continue
        event_id = alignment.sportsbook_event_id

        strength = compute_strength_exchange_divergence(
            divergence_type=div_event.divergence_type,
            lag_seconds=div_event.lag_seconds,
            exchange_probability=div_event.exchange_probability_threshold,
        )

        direction = "UP"
        if div_event.exchange_probability_threshold is not None and div_event.exchange_probability_threshold < 0.5:
            direction = "DOWN"

        minutes_to_tip: float | None = None
        time_bucket = "UNKNOWN"
        try:
            minutes_to_tip = _minutes_to_tip(event_id=event_id, commence_time_map=commence_time_map, now=now)
            time_bucket = compute_time_bucket(minutes_to_tip)
        except Exception:
            logger.warning(
                "Signal time bucket failed",
                extra={"event_id": event_id, "signal_type": "EXCHANGE_DIVERGENCE"},
            )

        dedupe_key = f"signal:exchange_divergence:{event_id}:{div_event.divergence_type}"

        signal = Signal(
            event_id=event_id,
            market="exchange",
            signal_type="EXCHANGE_DIVERGENCE",
            direction=direction,
            from_value=float(div_event.sportsbook_threshold_value or 0.0),
            to_value=float(div_event.exchange_probability_threshold or 0.0),
            from_price=None,
            to_price=None,
            window_minutes=lookback,
            books_affected=1,
            velocity_minutes=round((div_event.lag_seconds or 0) / 60.0, 2),
            time_bucket=time_bucket,
            strength_score=strength,
            metadata_json={
                "divergence_type": div_event.divergence_type,
                "lead_source": div_event.lead_source,
                "lag_seconds": div_event.lag_seconds,
                "exchange_probability": float(div_event.exchange_probability_threshold)
                if div_event.exchange_probability_threshold is not None
                else None,
                "sportsbook_threshold": float(div_event.sportsbook_threshold_value)
                if div_event.sportsbook_threshold_value is not None
                else None,
                "canonical_event_key": div_event.canonical_event_key,
                "minutes_to_tip": round(minutes_to_tip, 2) if minutes_to_tip is not None else None,
            },
        )
        candidate_by_event[event_id].append(
            DislocationCandidate(
                event_id=event_id,
                strength_score=strength,
                dedupe_key=dedupe_key,
                signal=signal,
            )
        )

    if not candidate_by_event:
        return []

    created: list[Signal] = []
    max_per_event = max(1, settings.exchange_divergence_max_signals_per_event)
    for event_id, candidates in candidate_by_event.items():
        ranked = sorted(candidates, key=lambda c: c.strength_score, reverse=True)
        for candidate in ranked[:max_per_event]:
            if await _dedupe_signal(redis, candidate.dedupe_key, settings.exchange_divergence_cooldown_seconds):
                continue
            db.add(candidate.signal)
            created.append(candidate.signal)

    if created:
        logger.info(
            "Exchange divergence signal detection completed",
            extra={"exchange_divergence_signals_created": len(created)},
        )

    return created


async def detect_market_movements(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
) -> list[Signal]:
    if not event_ids:
        return []

    commence_time_map = await _commence_time_by_event(db, event_ids)

    # Three queries total regardless of event count — was N*3 queries before
    all_created: list[Signal] = []
    all_created.extend(
        await _detect_line_move_signals(
            db,
            redis,
            event_ids,
            market="spreads",
            window_minutes=10,
            commence_time_map=commence_time_map,
        )
    )
    all_created.extend(
        await _detect_line_move_signals(
            db,
            redis,
            event_ids,
            market="totals",
            window_minutes=15,
            commence_time_map=commence_time_map,
        )
    )
    all_created.extend(
        await _detect_multibook_sync_signals(
            db,
            redis,
            event_ids,
            commence_time_map=commence_time_map,
        )
    )
    all_created.extend(await detect_dislocations(event_ids, db, redis, commence_time_map=commence_time_map))
    all_created.extend(await detect_steam_v2(event_ids, db, redis, commence_time_map=commence_time_map))
    all_created.extend(
        await _detect_live_shock_signals(
            db,
            redis,
            event_ids,
            commence_time_map=commence_time_map,
        )
    )

    if not all_created:
        return []

    from app.services.kalshi_gating import compute_kalshi_skew_gate
    for signal in all_created:
        skew = signal.metadata_json.get("exchange_liquidity_skew")
        gate_info = compute_kalshi_skew_gate(skew)
        signal.kalshi_liquidity_skew = gate_info["kalshi_liquidity_skew"]
        signal.kalshi_skew_bucket = gate_info["kalshi_skew_bucket"]
        signal.kalshi_gate_threshold = gate_info["kalshi_gate_threshold"]
        signal.kalshi_gate_mode = gate_info["kalshi_gate_mode"]
        signal.kalshi_gate_pass = gate_info["kalshi_gate_pass"]

    await db.commit()

    # Reload with ids so created_at values are available and sorted for downstream alerts.
    ids = [signal.id for signal in all_created]
    stmt = select(Signal).where(Signal.id.in_(ids)).order_by(desc(Signal.created_at))
    persisted = (await db.execute(stmt)).scalars().all()

    logger.info("Signal detection completed", extra={"signals_created": len(persisted)})
    return persisted
