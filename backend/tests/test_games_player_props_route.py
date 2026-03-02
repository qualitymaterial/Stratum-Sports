from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.game import Game
from app.models.player_prop_snapshot import PlayerPropSnapshot
from app.models.user import User


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "PropsRoutePass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_game_player_props_route_returns_latest_rows_and_filters(async_client: AsyncClient, db_session) -> None:
    token = await _register(async_client, "games-props-route@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    user = (await db_session.execute(select(User).where(User.email == "games-props-route@example.com"))).scalar_one()
    user.tier = "pro"
    await db_session.commit()

    now = datetime.now(UTC)
    commence_time = now + timedelta(hours=2)
    event_id = "event_games_props_route"
    db_session.add(
        Game(
            event_id=event_id,
            sport_key="basketball_nba",
            commence_time=commence_time,
            home_team="Golden State Warriors",
            away_team="Boston Celtics",
        )
    )

    db_session.add_all(
        [
            PlayerPropSnapshot(
                event_id=event_id,
                sport_key="basketball_nba",
                commence_time=commence_time,
                home_team="Golden State Warriors",
                away_team="Boston Celtics",
                sportsbook_key="book1",
                market="player_points",
                player_name="Stephen Curry",
                outcome_name="Over",
                line=27.5,
                price=-114,
                fetched_at=now - timedelta(minutes=10),
            ),
            # Newer duplicate key row should win.
            PlayerPropSnapshot(
                event_id=event_id,
                sport_key="basketball_nba",
                commence_time=commence_time,
                home_team="Golden State Warriors",
                away_team="Boston Celtics",
                sportsbook_key="book1",
                market="player_points",
                player_name="Stephen Curry",
                outcome_name="Over",
                line=28.5,
                price=-108,
                fetched_at=now - timedelta(minutes=2),
            ),
            PlayerPropSnapshot(
                event_id=event_id,
                sport_key="basketball_nba",
                commence_time=commence_time,
                home_team="Golden State Warriors",
                away_team="Boston Celtics",
                sportsbook_key="book1",
                market="player_assists",
                player_name="Stephen Curry",
                outcome_name="Over",
                line=6.5,
                price=-105,
                fetched_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await db_session.commit()

    response = await async_client.get(f"/api/v1/games/{event_id}/props", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 2
    points_row = next(row for row in payload if row["market"] == "player_points")
    assert points_row["line"] == 28.5
    assert points_row["price"] == -108

    filtered = await async_client.get(
        f"/api/v1/games/{event_id}/props?market=player_assists",
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    filtered_payload = filtered.json()
    assert len(filtered_payload) == 1
    assert filtered_payload[0]["market"] == "player_assists"
