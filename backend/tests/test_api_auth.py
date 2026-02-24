import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.models.user import User


@pytest.mark.asyncio
async def test_register_and_login_flow(async_client: AsyncClient, db_session: AsyncSession):
    test_email = "test-integration-auth@example.com"
    test_password = "SecurePassword123!"

    # 1. Register a new user
    reg_payload = {"email": test_email, "password": test_password}
    reg_resp = await async_client.post("/api/v1/auth/register", json=reg_payload)
    
    assert reg_resp.status_code == 200, f"Registration failed: {reg_resp.text}"
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == test_email
    assert reg_data["user"]["tier"] == "free"

    # Verify user exists in the DB (within the transaction)
    stmt = select(User).where(User.email == test_email)
    user_in_db = (await db_session.execute(stmt)).scalar_one_or_none()
    assert user_in_db is not None
    assert user_in_db.email == test_email

    # 2. Login with the new user
    login_payload = {"email": test_email, "password": test_password}
    login_resp = await async_client.post("/api/v1/auth/login", json=login_payload)
    
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    login_data = login_resp.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == test_email

    # 3. Test wrong password
    bad_login = await async_client.post(
        "/api/v1/auth/login", 
        json={"email": test_email, "password": "wrongpassword"}
    )
    assert bad_login.status_code == 401

    # 4. Fetch /me endpoint
    token = login_data["access_token"]
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == test_email


@pytest.mark.asyncio
async def test_password_reset_request_and_confirm(async_client: AsyncClient, db_session: AsyncSession):
    test_email = "password-reset@example.com"
    old_password = "SecurePassword123!"
    new_password = "UpdatedPassword456!"

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": test_email, "password": old_password},
    )
    assert reg_resp.status_code == 200

    request_resp = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": test_email},
    )
    assert request_resp.status_code == 200, request_resp.text
    request_payload = request_resp.json()
    assert "message" in request_payload
    assert request_payload.get("reset_token")

    token_stmt = select(PasswordResetToken).order_by(PasswordResetToken.created_at.desc())
    token_row = (await db_session.execute(token_stmt)).scalars().first()
    assert token_row is not None
    assert token_row.used_at is None

    reset_token = request_payload["reset_token"]
    confirm_resp = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": new_password},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    old_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": old_password},
    )
    assert old_login.status_code == 401

    new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": new_password},
    )
    assert new_login.status_code == 200

    reuse_resp = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "AnotherPass789!"},
    )
    assert reuse_resp.status_code == 400


@pytest.mark.asyncio
async def test_password_reset_request_unknown_email_returns_generic(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown-user@example.com"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "message" in payload
    assert payload.get("reset_token") is None
