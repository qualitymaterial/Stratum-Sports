"""Context score — line-velocity proxy for injury news.

Without a live injury feed, sharp/rapid spread moves that involve many books
are used as a proxy signal: if the consensus spread has shifted significantly
in the last 30 minutes across 3+ books, there is a non-trivial chance that
injury news is priced in.
"""
from datetime import UTC, datetime, timedelta
from statistics import stdev

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.services.context_score.injury_feed import get_sportsdataio_injury_context
from app.core.config import get_settings

settings = get_settings()


async def _heuristic_injury_context(
    db: AsyncSession,
    event_id: str,
    *,
    fallback_reason: str | None = None,
) -> dict:
    """Existing spread-velocity heuristic used as resilient fallback."""
    window_minutes = 30
    start_ts = datetime.now(UTC) - timedelta(minutes=window_minutes)

    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market == "spreads",
            OddsSnapshot.fetched_at >= start_ts,
            OddsSnapshot.line.is_not(None),
        )
        .order_by(OddsSnapshot.fetched_at)
    )
    snaps = (await db.execute(stmt)).scalars().all()

    if len(snaps) < 4:
        return {
            "event_id": event_id,
            "component": "injuries",
            "status": "insufficient_data",
            "score": None,
            "notes": "Not enough recent snapshots to evaluate.",
        }

    lines = [float(s.line) for s in snaps]
    books = {s.sportsbook_key for s in snaps}
    total_move = abs(lines[-1] - lines[0])
    velocity = total_move / window_minutes
    spread_std = stdev(lines) if len(lines) > 1 else 0.0

    # Score 0-100: high = high likelihood of injury-priced move
    move_score = min(50.0, total_move * 10)
    book_score = min(30.0, len(books) * 6.0)
    velocity_score = min(20.0, velocity * 40)
    score = int(round(move_score + book_score + velocity_score))

    notes = "Derived from spread-line velocity. No live injury feed connected."
    if fallback_reason:
        notes = f"{notes} Live injury feed unavailable ({fallback_reason}); heuristic fallback used."

    return {
        "event_id": event_id,
        "component": "injuries",
        "status": "computed",
        "score": score,
        "details": {
            "source": "heuristic",
            "spread_move_pts": round(total_move, 2),
            "spread_std": round(spread_std, 3),
            "velocity_pts_per_min": round(velocity, 4),
            "books_sampled": len(books),
        },
        "notes": notes,
    }


async def get_injury_context(db: AsyncSession, event_id: str) -> dict:
    provider = settings.injury_feed_provider.strip().lower()
    if provider == "sportsdataio":
        game_stmt = select(Game).where(Game.event_id == event_id)
        game = (await db.execute(game_stmt)).scalar_one_or_none()
        if game is not None:
            live_context = await get_sportsdataio_injury_context(game)
            if live_context is not None:
                return live_context
            return await _heuristic_injury_context(db, event_id, fallback_reason="sportsdataio_unavailable")

    return await _heuristic_injury_context(db, event_id)
