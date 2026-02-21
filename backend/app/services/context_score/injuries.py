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

from app.models.odds_snapshot import OddsSnapshot


async def get_injury_context(db: AsyncSession, event_id: str) -> dict:
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

    return {
        "event_id": event_id,
        "component": "injuries",
        "status": "computed",
        "score": score,
        "details": {
            "spread_move_pts": round(total_move, 2),
            "spread_std": round(spread_std, 3),
            "velocity_pts_per_min": round(velocity, 4),
            "books_sampled": len(books),
        },
        "notes": "Derived from spread-line velocity. No live injury feed connected.",
    }
