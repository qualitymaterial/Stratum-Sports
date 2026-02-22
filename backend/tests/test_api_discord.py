from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DiscordPass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _register_pro_user(async_client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    token = await _register(async_client, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.tier = "pro"
    await db_session.commit()
    return token


async def test_discord_connection_rejects_non_discord_webhook(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register_pro_user(async_client, db_session, "discord-invalid@example.com")
    response = await async_client.put(
        "/api/v1/discord/connection",
        json={
            "webhook_url": "https://example.com/not-discord",
            "is_enabled": True,
            "alert_spreads": True,
            "alert_totals": True,
            "alert_multibook": True,
            "min_strength": 60,
            "thresholds": {
                "min_books_affected": 1,
                "max_dispersion": None,
                "cooldown_minutes": 15,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert "Discord webhook endpoint" in response.json()["detail"]


async def test_discord_connection_accepts_valid_discord_webhook(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register_pro_user(async_client, db_session, "discord-valid@example.com")
    response = await async_client.put(
        "/api/v1/discord/connection",
        json={
            "webhook_url": "https://discord.com/api/webhooks/1234567890/abcdef",
            "is_enabled": True,
            "alert_spreads": True,
            "alert_totals": True,
            "alert_multibook": True,
            "min_strength": 60,
            "thresholds": {
                "min_books_affected": 1,
                "max_dispersion": None,
                "cooldown_minutes": 15,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["webhook_url"].startswith("https://discord.com/api/webhooks/")
