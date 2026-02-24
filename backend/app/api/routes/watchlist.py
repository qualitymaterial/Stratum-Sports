from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tier import is_pro
from app.models.game import Game
from app.models.user import User
from app.models.watchlist import Watchlist

router = APIRouter()
settings = get_settings()


@router.get("")
async def list_watchlist(
    sport_key: str | None = Query(
        None,
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    stmt = select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at.desc())
    items = (await db.execute(stmt)).scalars().all()

    event_ids = [item.event_id for item in items]
    games_stmt = select(Game).where(Game.event_id.in_(event_ids)) if event_ids else None
    if games_stmt is not None and sport_key:
        games_stmt = games_stmt.where(Game.sport_key == sport_key)
    game_map = {}
    if games_stmt is not None:
        for game in (await db.execute(games_stmt)).scalars().all():
            game_map[game.event_id] = game

    payload = []
    for item in items:
        game = game_map.get(item.event_id)
        if sport_key and game is None:
            continue
        payload.append(
            {
                "id": item.id,
                "event_id": item.event_id,
                "created_at": item.created_at,
                "game": {
                    "sport_key": game.sport_key,
                    "home_team": game.home_team,
                    "away_team": game.away_team,
                    "commence_time": game.commence_time,
                }
                if game is not None
                else None,
            }
        )
    return payload


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

    if not is_pro(user):
        await db.execute(select(User.id).where(User.id == user.id).with_for_update())
        count_stmt = select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)
        count = (await db.execute(count_stmt)).scalar_one()
        if count >= settings.free_watchlist_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Free tier watchlist limit is {settings.free_watchlist_limit}",
            )

    insert_stmt = (
        pg_insert(Watchlist)
        .values(user_id=user.id, event_id=event_id)
        .on_conflict_do_nothing(index_elements=[Watchlist.user_id, Watchlist.event_id])
        .returning(Watchlist.id)
    )
    inserted_id = (await db.execute(insert_stmt)).scalar_one_or_none()
    await db.commit()
    if inserted_id is None:
        return {"status": "exists", "event_id": event_id}
    return {"status": "added", "event_id": event_id, "id": inserted_id}


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
