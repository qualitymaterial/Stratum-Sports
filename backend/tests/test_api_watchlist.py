"""Integration tests for watchlist endpoints."""
from datetime import UTC, datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _register(async_client: AsyncClient, email: str = "watch-test@example.com") -> str:
    """Register user, return token."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "WatchPass1!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _seed_game(
    db_session: AsyncSession,
    event_id: str = "test_event_001",
    sport_key: str = "basketball_nba",
) -> Game:
    """Insert a game row directly so watchlist tests have something to track."""
    game = Game(
        event_id=event_id,
        sport_key=sport_key,
        commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=UTC),
        home_team="Lakers",
        away_team="Celtics",
    )
    db_session.add(game)
    await db_session.flush()
    return game


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

async def test_watchlist_empty_on_new_user(async_client: AsyncClient):
    token = await _register(async_client)
    resp = await async_client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_watchlist_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/watchlist")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

async def test_add_nonexistent_game_returns_404(async_client: AsyncClient):
    token = await _register(async_client, "watch-404@example.com")
    resp = await async_client.post(
        "/api/v1/watchlist/does_not_exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_add_and_list_watchlist_item(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    game = await _seed_game(db_session, "event_add_001")
    token = await _register(async_client, "watch-add@example.com")

    add_resp = await async_client.post(
        f"/api/v1/watchlist/{game.event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["status"] == "added"

    list_resp = await async_client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["event_id"] == game.event_id
    assert items[0]["game"]["home_team"] == "Lakers"
    assert items[0]["game"]["sport_key"] == "basketball_nba"


async def test_list_watchlist_filters_by_sport_key(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    nba_game = await _seed_game(db_session, "event_watch_nba", sport_key="basketball_nba")
    nfl_game = await _seed_game(db_session, "event_watch_nfl", sport_key="americanfootball_nfl")
    token = await _register(async_client, "watch-sport-filter@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for event_id in (nba_game.event_id, nfl_game.event_id):
        add_resp = await async_client.post(f"/api/v1/watchlist/{event_id}", headers=headers)
        assert add_resp.status_code == 200

    nba_resp = await async_client.get("/api/v1/watchlist?sport_key=basketball_nba", headers=headers)
    assert nba_resp.status_code == 200
    nba_items = nba_resp.json()
    assert len(nba_items) == 1
    assert nba_items[0]["event_id"] == nba_game.event_id

    nfl_resp = await async_client.get("/api/v1/watchlist?sport_key=americanfootball_nfl", headers=headers)
    assert nfl_resp.status_code == 200
    nfl_items = nfl_resp.json()
    assert len(nfl_items) == 1
    assert nfl_items[0]["event_id"] == nfl_game.event_id


async def test_add_duplicate_returns_exists(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    game = await _seed_game(db_session, "event_dup_001")
    token = await _register(async_client, "watch-dup@example.com")

    await async_client.post(
        f"/api/v1/watchlist/{game.event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp2 = await async_client.post(
        f"/api/v1/watchlist/{game.event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "exists"


async def test_free_tier_watchlist_limit(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Free users cannot exceed the 3-game watchlist limit."""
    token = await _register(async_client, "watch-limit@example.com")

    for i in range(1, 5):
        game = await _seed_game(db_session, f"event_limit_{i:03d}")
        resp = await async_client.post(
            f"/api/v1/watchlist/{game.event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if i <= 3:
            assert resp.status_code == 200, f"item {i} should succeed"
        else:
            assert resp.status_code == 403, f"item {i} should be blocked by free limit"
            assert "limit" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

async def test_remove_watchlist_item(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    game = await _seed_game(db_session, "event_rm_001")
    token = await _register(async_client, "watch-rm@example.com")

    await async_client.post(
        f"/api/v1/watchlist/{game.event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    del_resp = await async_client.delete(
        f"/api/v1/watchlist/{game.event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "removed"

    list_resp = await async_client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.json() == []


async def test_remove_nonexistent_returns_404(async_client: AsyncClient):
    token = await _register(async_client, "watch-rm404@example.com")
    resp = await async_client.delete(
        "/api/v1/watchlist/does_not_exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
