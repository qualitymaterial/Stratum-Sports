"""Quote Move Ledger — detects line/price changes per venue and logs them."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_venue_tier
from app.models.odds_snapshot import OddsSnapshot
from app.models.quote_move_event import QuoteMoveEvent

logger = logging.getLogger(__name__)


async def detect_quote_moves(
    db: AsyncSession,
    snapshots: list[OddsSnapshot],
    commence_times: dict[str, datetime],
) -> list[QuoteMoveEvent]:
    """Compare each new snapshot against the previous snapshot for the same
    (event_id, market, outcome_name, sportsbook_key) and create QuoteMoveEvent
    rows for any line or price change.

    Returns the list of QuoteMoveEvent objects added to the session (not yet committed).
    """
    if not snapshots:
        return []

    moves: list[QuoteMoveEvent] = []

    # Batch-fetch previous snapshots: for each new snapshot, find the most recent
    # prior snapshot with the same composite key.
    for snap in snapshots:
        stmt = (
            select(OddsSnapshot)
            .where(
                OddsSnapshot.event_id == snap.event_id,
                OddsSnapshot.market == snap.market,
                OddsSnapshot.outcome_name == snap.outcome_name,
                OddsSnapshot.sportsbook_key == snap.sportsbook_key,
                OddsSnapshot.fetched_at < snap.fetched_at,
            )
            .order_by(OddsSnapshot.fetched_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        prev = result.scalar_one_or_none()
        if prev is None:
            continue

        line_changed = snap.line != prev.line
        price_changed = snap.price != prev.price

        if not line_changed and not price_changed:
            continue

        now_utc = snap.fetched_at
        commence_time = commence_times.get(snap.event_id)
        mtt = None
        if commence_time is not None:
            mtt = (commence_time - now_utc).total_seconds() / 60.0

        delta = None
        if snap.line is not None and prev.line is not None:
            delta = snap.line - prev.line

        price_delta = None
        if snap.price is not None and prev.price is not None:
            price_delta = float(snap.price) - float(prev.price)

        move = QuoteMoveEvent(
            event_id=snap.event_id,
            market_key=snap.market,
            outcome_name=snap.outcome_name,
            venue=snap.sportsbook_key,
            venue_tier=get_venue_tier(snap.sportsbook_key),
            old_line=prev.line,
            new_line=snap.line,
            delta=delta,
            old_price=float(prev.price) if prev.price is not None else None,
            new_price=float(snap.price) if snap.price is not None else None,
            price_delta=price_delta,
            timestamp=now_utc,
            minutes_to_tip=mtt,
        )
        db.add(move)
        moves.append(move)

    if moves:
        logger.info("Quote moves detected", extra={"count": len(moves)})

    return moves
