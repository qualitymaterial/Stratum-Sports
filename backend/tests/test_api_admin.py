from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AdminRoutePass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_admin_overview_requires_admin(
    async_client: AsyncClient,
) -> None:
    token = await _register(async_client, "admin-route-free@example.com")
    response = await async_client.get(
        "/api/v1/admin/overview?days=7&cycle_limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


async def test_admin_overview_returns_payload_for_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-route-ok@example.com")
    user = (await db_session.execute(select(User).where(User.email == "admin-route-ok@example.com"))).scalar_one()
    user.is_admin = True
    user.tier = "pro"
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/admin/overview?days=7&cycle_limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "report" in payload
    assert "recent_cycles" in payload
    assert payload["report"]["days"] == 7
