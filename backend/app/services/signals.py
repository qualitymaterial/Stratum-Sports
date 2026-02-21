import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Iterable

from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class BookMove:
    sportsbook_key: str
    from_value: float
    to_value: float
    direction: str
    velocity_minutes: float


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
) -> tuple[int, dict]:
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


def serialize_signal(signal: Signal, *, pro_user: bool) -> dict:
    metadata = signal.metadata_json or {}
    if not pro_user:
        metadata = {k: v for k, v in metadata.items() if k not in {"books", "components"}}

    return {
        "id": signal.id,
        "event_id": signal.event_id,
        "market": signal.market,
        "signal_type": signal.signal_type,
        "direction": signal.direction,
        "from_value": signal.from_value,
        "to_value": signal.to_value,
        "from_price": signal.from_price,
        "to_price": signal.to_price,
        "window_minutes": signal.window_minutes,
        "books_affected": signal.books_affected,
        "velocity_minutes": signal.velocity_minutes if pro_user else None,
        "strength_score": signal.strength_score,
        "created_at": signal.created_at,
        "metadata": metadata,
    }


async def _detect_line_move_signals(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
    market: str,
    window_minutes: int,
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

        strength, components = compute_strength_score(
            magnitude=magnitude,
            velocity_minutes=velocity_minutes,
            window_minutes=window_minutes,
            books_affected=len(books),
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
            strength_score=strength,
            metadata_json={
                "outcome_name": outcome_name,
                "magnitude": round(magnitude, 3),
                "key_cross": crosses,
                "books": books,
                "components": components,
            },
        )
        db.add(signal)
        created.append(signal)

    return created


async def _detect_multibook_sync_signals(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
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

        strength, components = compute_strength_score(
            magnitude=magnitude,
            velocity_minutes=velocity,
            window_minutes=window_minutes,
            books_affected=len(moves),
        )

        books = sorted({m.sportsbook_key for m in moves})
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
            strength_score=strength,
            metadata_json={
                "outcome_name": outcome_name,
                "books": books,
                "magnitude": round(magnitude, 3),
                "components": components,
            },
        )
        db.add(signal)
        created.append(signal)

    return created


async def detect_market_movements(
    db: AsyncSession,
    redis: Redis | None,
    event_ids: list[str],
) -> list[Signal]:
    if not event_ids:
        return []

    # Three queries total regardless of event count — was N*3 queries before
    all_created: list[Signal] = []
    all_created.extend(
        await _detect_line_move_signals(db, redis, event_ids, market="spreads", window_minutes=10)
    )
    all_created.extend(
        await _detect_line_move_signals(db, redis, event_ids, market="totals", window_minutes=15)
    )
    all_created.extend(await _detect_multibook_sync_signals(db, redis, event_ids))

    if not all_created:
        return []

    await db.commit()

    # Reload with ids so created_at values are available and sorted for downstream alerts.
    ids = [signal.id for signal in all_created]
    stmt = select(Signal).where(Signal.id.in_(ids)).order_by(desc(Signal.created_at))
    persisted = (await db.execute(stmt)).scalars().all()

    logger.info("Signal detection completed", extra={"signals_created": len(persisted)})
    return persisted
