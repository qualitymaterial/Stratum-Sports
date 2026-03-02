from sqlalchemy.ext.asyncio import AsyncSession

from app.services.context_score.cross_market import get_cross_market_context
from app.services.context_score.injuries import get_injury_context
from app.services.context_score.pace import get_pace_context
from app.services.context_score.player_props import get_player_props_context


async def build_context_score(db: AsyncSession, event_id: str) -> dict:
    """Run all context-score components and return results.

    NOTE:
    Async SQLAlchemy sessions cannot safely execute concurrent statements on the
    same connection, so these components are awaited sequentially.
    """
    injury = await get_injury_context(db, event_id)
    props = await get_player_props_context(db, event_id)
    pace = await get_pace_context(db, event_id)
    cross_market = await get_cross_market_context(db, event_id)
    return {
        "event_id": event_id,
        "components": [injury, props, pace, cross_market],
    }
