import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.context_score.injuries import get_injury_context
from app.services.context_score.pace import get_pace_context
from app.services.context_score.player_props import get_player_props_context


async def build_context_score(db: AsyncSession, event_id: str) -> dict:
    """Run all three context-score components concurrently and return results."""
    injury, props, pace = await asyncio.gather(
        get_injury_context(db, event_id),
        get_player_props_context(db, event_id),
        get_pace_context(db, event_id),
    )
    return {
        "event_id": event_id,
        "components": [injury, props, pace],
    }
