from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "IntelSignal1!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_intel_quality_accepts_live_shock_signal_type(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "intel-live-shock@example.com")
    user = (await db_session.execute(select(User).where(User.email == "intel-live-shock@example.com"))).scalar_one()
    user.tier = "pro"
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/intel/signals/quality?days=7&signal_type=LIVE_SHOCK",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


async def test_intel_quality_rejects_unknown_signal_type(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "intel-unknown-signal@example.com")
    user = (await db_session.execute(select(User).where(User.email == "intel-unknown-signal@example.com"))).scalar_one()
    user.tier = "pro"
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/intel/signals/quality?days=7&signal_type=NOT_A_SIGNAL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
