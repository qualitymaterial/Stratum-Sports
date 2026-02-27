import pytest
from datetime import UTC, datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.user import User


async def _create_admin_user(
    db: AsyncSession,
    email: str,
    admin_role: str = "super_admin",
    last_login_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=get_password_hash("Str0ng!Pass99"),
        tier="pro",
        is_admin=True,
        admin_role=admin_role,
        last_login_at=last_login_at,
    )
    db.add(user)
    await db.flush()
    return user


async def _get_admin_token(async_client: AsyncClient, email: str) -> str:
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Str0ng!Pass99"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_stale_admin_endpoint_returns_stale_users(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admins with NULL last_login_at should appear in stale list."""
    # Create an admin who has never logged in
    await _create_admin_user(db_session, "stale@example.com", last_login_at=None)
    # Create an admin who logged in recently (the one we'll use to authenticate)
    await _create_admin_user(
        db_session,
        "active@example.com",
        last_login_at=datetime.now(UTC),
    )
    await db_session.commit()

    token = await _get_admin_token(async_client, "active@example.com")
    resp = await async_client.get(
        "/api/v1/admin/access-review/stale",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["threshold_days"] == 30
    emails = [item["email"] for item in data["items"]]
    assert "stale@example.com" in emails
    assert "active@example.com" not in emails


@pytest.mark.asyncio
async def test_stale_admin_excludes_recent_logins(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admins who logged in within threshold should not appear."""
    await _create_admin_user(
        db_session,
        "recent@example.com",
        last_login_at=datetime.now(UTC) - timedelta(days=5),
    )
    await _create_admin_user(
        db_session,
        "caller@example.com",
        last_login_at=datetime.now(UTC),
    )
    await db_session.commit()

    token = await _get_admin_token(async_client, "caller@example.com")
    resp = await async_client.get(
        "/api/v1/admin/access-review/stale?days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    emails = [item["email"] for item in resp.json()["items"]]
    assert "recent@example.com" not in emails


@pytest.mark.asyncio
async def test_stale_admin_requires_admin_permission(async_client: AsyncClient) -> None:
    """Non-admin users should be rejected."""
    # Register as regular user
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "regular@example.com", "password": "Str0ng!Pass99"},
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/admin/access-review/stale",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
