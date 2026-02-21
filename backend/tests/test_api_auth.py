import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
