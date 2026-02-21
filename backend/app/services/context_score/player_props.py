"""Context score — h2h vs spread divergence as a player-props proxy.

Without a live props feed we detect divergence between the moneyline and
spread markets. When the spread favorite and moneyline favorite disagree,
or when their movements decouple, it often reflects player-level news being
priced into one market before the other.
"""
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot


async def get_player_props_context(db: AsyncSession, event_id: str) -> dict:
    window_minutes = 60
    start_ts = datetime.now(UTC) - timedelta(minutes=window_minutes)

    game_stmt = select(Game).where(Game.event_id == event_id)
    game = (await db.execute(game_stmt)).scalar_one_or_none()
    if game is None:
        return {
            "event_id": event_id,
            "component": "player_props",
            "status": "insufficient_data",
            "score": None,
            "notes": "Game not found.",
        }

    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market.in_(["spreads", "h2h"]),
            OddsSnapshot.fetched_at >= start_ts,
        )
        .order_by(OddsSnapshot.fetched_at)
    )
    snaps = (await db.execute(stmt)).scalars().all()

    spread_snaps = [s for s in snaps if s.market == "spreads" and s.line is not None]
    h2h_home = [float(s.price) for s in snaps if s.market == "h2h" and s.outcome_name == game.home_team]
    h2h_away = [float(s.price) for s in snaps if s.market == "h2h" and s.outcome_name == game.away_team]

    if len(spread_snaps) < 2 or not h2h_home or not h2h_away:
        return {
            "event_id": event_id,
            "component": "player_props",
            "status": "insufficient_data",
            "score": None,
            "notes": "Not enough market data to assess divergence.",
        }

    spread_lines = [float(s.line) for s in spread_snaps]
    spread_drift = spread_lines[-1] - spread_lines[0]

    avg_home_ml = mean(h2h_home)
    avg_away_ml = mean(h2h_away)

    # Spread favorite: negative spread = home favored
    spread_favors_home = spread_lines[-1] < 0
    # ML favorite: lower absolute American odds = more favored (negative = favored)
    ml_favors_home = avg_home_ml < avg_away_ml

    alignment = spread_favors_home == ml_favors_home
    # Drift in opposite direction to moneyline implies props/injury pressure
    ml_drift = (h2h_home[-1] - h2h_home[0]) if len(h2h_home) > 1 else 0.0
    divergence = abs(spread_drift) > 0.5 and (spread_drift > 0) != (ml_drift < 0)

    # Score: high = strong divergence between spread and moneyline markets
    base = 20 if not alignment else 5
    drift_score = min(50.0, abs(spread_drift) * 10)
    divergence_bonus = 30 if divergence else 0
    score = int(min(100, base + drift_score + divergence_bonus))

    return {
        "event_id": event_id,
        "component": "player_props",
        "status": "computed",
        "score": score,
        "details": {
            "spread_drift": round(spread_drift, 2),
            "ml_home_avg": round(avg_home_ml, 1),
            "ml_away_avg": round(avg_away_ml, 1),
            "markets_aligned": alignment,
            "divergence_detected": divergence,
        },
        "notes": "Derived from spread/moneyline divergence. No live props feed connected.",
    }
