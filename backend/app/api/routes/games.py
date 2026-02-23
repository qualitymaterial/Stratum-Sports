import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_pro_user
from app.core.database import get_db
from app.models.odds_snapshot import OddsSnapshot
from app.models.user import User
from app.services.market_data import build_game_detail, list_upcoming_games

router = APIRouter()


@router.get("")
async def list_games(
    sport_key: str | None = Query(
        None,
        pattern="^(basketball_nba|basketball_ncaab|americanfootball_nfl)$",
    ),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict]:
    games = await list_upcoming_games(db, limit=40, sport_key=sport_key)
    return [
        {
            "event_id": game.event_id,
            "sport_key": game.sport_key,
            "commence_time": game.commence_time,
            "home_team": game.home_team,
            "away_team": game.away_team,
        }
        for game in games
    ]


@router.get("/{event_id}")
async def game_detail(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    detail = await build_game_detail(db, user, event_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return detail


@router.get("/{event_id}/export.csv")
async def export_market_csv(
    event_id: str,
    market: str = Query(..., pattern="^(spreads|totals|h2h)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> StreamingResponse:
    stmt = (
        select(OddsSnapshot)
        .where(
            and_(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.market == market,
                OddsSnapshot.fetched_at >= datetime.now(UTC) - timedelta(days=7),
            )
        )
        .order_by(OddsSnapshot.fetched_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "event_id",
            "sport_key",
            "commence_time",
            "home_team",
            "away_team",
            "sportsbook_key",
            "market",
            "outcome_name",
            "line",
            "price",
            "fetched_at",
        ]
    )

    for row in rows:
        writer.writerow(
            [
                row.event_id,
                row.sport_key,
                row.commence_time.isoformat(),
                row.home_team,
                row.away_team,
                row.sportsbook_key,
                row.market,
                row.outcome_name,
                row.line,
                row.price,
                row.fetched_at.isoformat(),
            ]
        )

    buffer.seek(0)
    filename = f"{event_id}-{market}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
