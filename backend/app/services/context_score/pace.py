"""Context score — pace projection from totals-line movement.

Uses the standard deviation and direction of recent totals snapshots as a
proxy for expected-pace uncertainty. A rising total with low spread movement
suggests an up-tempo game is being priced in; high deviation suggests books
disagree on pace.
"""
from datetime import UTC, datetime, timedelta
from statistics import mean, stdev

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot


async def get_pace_context(db: AsyncSession, event_id: str) -> dict:
    window_minutes = 60
    start_ts = datetime.now(UTC) - timedelta(minutes=window_minutes)

    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market == "totals",
            OddsSnapshot.fetched_at >= start_ts,
            OddsSnapshot.line.is_not(None),
        )
        .order_by(OddsSnapshot.fetched_at)
    )
    snaps = (await db.execute(stmt)).scalars().all()

    if len(snaps) < 4:
        return {
            "event_id": event_id,
            "component": "pace",
            "status": "insufficient_data",
            "score": None,
            "notes": "Not enough totals snapshots to project pace.",
        }

    lines = [float(s.line) for s in snaps]
    consensus = mean(lines)
    dispersion = stdev(lines) if len(lines) > 1 else 0.0
    drift = lines[-1] - lines[0]  # positive = total rising (up-tempo signal)

    # Score: high = meaningful pace signal (strong drift + low dispersion)
    drift_score = min(50.0, abs(drift) * 10)
    # Low dispersion means books agree → stronger signal
    agreement_score = max(0.0, 30.0 - dispersion * 20)
    direction_bonus = 10.0 if drift > 0 else 5.0
    score = int(round(min(100.0, drift_score + agreement_score + direction_bonus)))

    return {
        "event_id": event_id,
        "component": "pace",
        "status": "computed",
        "score": score,
        "details": {
            "consensus_total": round(consensus, 1),
            "total_drift_pts": round(drift, 2),
            "book_dispersion": round(dispersion, 3),
            "direction": "UP" if drift > 0 else "DOWN" if drift < 0 else "FLAT",
            "snapshots_used": len(snaps),
        },
        "notes": "Derived from totals-line drift and cross-book consensus.",
    }
