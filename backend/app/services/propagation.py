"""Propagation Event Engine — tracks how line moves spread across venues."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import pstdev

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
from app.models.propagation_event import PropagationEvent
from app.models.quote_move_event import QuoteMoveEvent

logger = logging.getLogger(__name__)

PROPAGATION_WINDOW_MINUTES = 5


def _dispersion(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return float(pstdev(values))


async def detect_propagation_events(
    db: AsyncSession,
    event_ids: list[str],
    commence_time_map: dict[str, datetime] | None = None,
) -> list[PropagationEvent]:
    """For each (event_id, market_key, outcome_name), look at recent quote moves
    to identify an origin venue and measure adoption across the market.

    Returns the list of PropagationEvent objects added to the session (not yet committed).
    """
    if not event_ids:
        return []

    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=PROPAGATION_WINDOW_MINUTES)

    # 1. Pull recent quote_move_events for the given events
    stmt = (
        select(QuoteMoveEvent)
        .where(
            QuoteMoveEvent.event_id.in_(event_ids),
            QuoteMoveEvent.timestamp >= cutoff,
            QuoteMoveEvent.delta.isnot(None),
        )
        .order_by(QuoteMoveEvent.timestamp.asc())
    )
    result = await db.execute(stmt)
    moves = result.scalars().all()

    if not moves:
        return []

    # 2. Group by (event_id, market_key, outcome_name)
    grouped: dict[tuple[str, str, str], list[QuoteMoveEvent]] = defaultdict(list)
    for move in moves:
        key = (move.event_id, move.market_key, move.outcome_name)
        grouped[key].append(move)

    propagation_events: list[PropagationEvent] = []

    for (event_id, market_key, outcome_name), group_moves in grouped.items():
        if len(group_moves) < 2:
            continue

        # 3. Origin = earliest move
        origin = group_moves[0]
        origin_direction = 1.0 if origin.delta > 0 else -1.0

        # 4. Count venues that moved in the same direction
        adopters: set[str] = set()
        all_venues: set[str] = set()
        for m in group_moves:
            all_venues.add(m.venue)
            if m.delta is not None and (m.delta * origin_direction) > 0:
                adopters.add(m.venue)

        # Get total active venues from current snapshots (not just movers)
        venue_stmt = (
            select(OddsSnapshot.sportsbook_key)
            .where(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.market == market_key,
                OddsSnapshot.outcome_name == outcome_name,
                OddsSnapshot.fetched_at >= cutoff,
            )
            .distinct()
        )
        venue_result = await db.execute(venue_stmt)
        total_active_venues = len(venue_result.scalars().all())
        total_active_venues = max(total_active_venues, len(all_venues))

        adoption_count = len(adopters)
        adoption_percent = adoption_count / total_active_venues if total_active_venues > 0 else 0.0

        # 6. Dispersion before (lines at the time of the origin move)
        before_cutoff = origin.timestamp - timedelta(minutes=1)
        before_stmt = (
            select(OddsSnapshot.line)
            .where(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.market == market_key,
                OddsSnapshot.outcome_name == outcome_name,
                OddsSnapshot.fetched_at <= origin.timestamp,
                OddsSnapshot.fetched_at >= before_cutoff - timedelta(minutes=PROPAGATION_WINDOW_MINUTES),
                OddsSnapshot.line.isnot(None),
            )
        )
        before_result = await db.execute(before_stmt)
        before_lines = [float(row[0]) for row in before_result.all()]
        dispersion_before = _dispersion(before_lines)

        # Dispersion after (current latest lines per venue)
        after_stmt = (
            select(OddsSnapshot.line)
            .where(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.market == market_key,
                OddsSnapshot.outcome_name == outcome_name,
                OddsSnapshot.fetched_at >= cutoff,
                OddsSnapshot.line.isnot(None),
            )
        )
        after_result = await db.execute(after_stmt)
        after_lines = [float(row[0]) for row in after_result.all()]
        dispersion_after = _dispersion(after_lines)

        # minutes_to_tip
        mtt = None
        if commence_time_map and event_id in commence_time_map:
            mtt = (commence_time_map[event_id] - now).total_seconds() / 60.0

        prop_event = PropagationEvent(
            event_id=event_id,
            market_key=market_key,
            outcome_name=outcome_name,
            origin_venue=origin.venue,
            origin_tier=origin.venue_tier,
            origin_delta=origin.delta,
            origin_timestamp=origin.timestamp,
            adoption_percent=round(adoption_percent, 4),
            adoption_count=adoption_count,
            total_venues=total_active_venues,
            dispersion_before=dispersion_before,
            dispersion_after=dispersion_after,
            minutes_to_tip=mtt,
        )
        db.add(prop_event)
        propagation_events.append(prop_event)

    if propagation_events:
        logger.info("Propagation events detected", extra={"count": len(propagation_events)})

    return propagation_events
