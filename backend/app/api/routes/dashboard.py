from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.market_data import build_dashboard_cards

router = APIRouter()


@router.get("/cards")
async def get_dashboard_cards(
    sport_key: str = Query(
        "basketball_nba",
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return await build_dashboard_cards(db, user, sport_key=sport_key)
