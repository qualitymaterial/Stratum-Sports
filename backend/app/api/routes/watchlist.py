from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.game import Game
from app.models.user import User
from app.models.watchlist import Watchlist

router = APIRouter()
settings = get_settings()


@router.get("")
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    stmt = select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at.desc())
    items = (await db.execute(stmt)).scalars().all()

    event_ids = [item.event_id for item in items]
    games_stmt = select(Game).where(Game.event_id.in_(event_ids)) if event_ids else None
    game_map = {}
    if games_stmt is not None:
        for game in (await db.execute(games_stmt)).scalars().all():
            game_map[game.event_id] = game

    return [
        {
            "id": item.id,
            "event_id": item.event_id,
            "created_at": item.created_at,
            "game": {
                "home_team": game_map[item.event_id].home_team,
                "away_team": game_map[item.event_id].away_team,
                "commence_time": game_map[item.event_id].commence_time,
            }
            if item.event_id in game_map
            else None,
        }
        for item in items
    ]


@router.post("/{event_id}")
async def add_watchlist_item(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    game_stmt = select(Game).where(Game.event_id == event_id)
    game = (await db.execute(game_stmt)).scalar_one_or_none()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    existing_stmt = select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.event_id == event_id)
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        return {"status": "exists", "event_id": event_id}

    if user.tier != "pro":
        count_stmt = select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)
        count = (await db.execute(count_stmt)).scalar_one()
        if count >= settings.free_watchlist_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Free tier watchlist limit is {settings.free_watchlist_limit}",
            )

    item = Watchlist(user_id=user.id, event_id=event_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"status": "added", "event_id": event_id, "id": item.id}


@router.delete("/{event_id}")
async def remove_watchlist_item(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.event_id == event_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    await db.delete(item)
    await db.commit()
    return {"status": "removed", "event_id": event_id}
