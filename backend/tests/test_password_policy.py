import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_weak_password_rejected(async_client: AsyncClient) -> None:
    """Short, lowercase-only password should be rejected."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short1"},
    )
    assert resp.status_code == 422  # pydantic min_length=10 rejects before handler


@pytest.mark.asyncio
async def test_register_no_uppercase_rejected(async_client: AsyncClient) -> None:
    """Password missing uppercase should be rejected by policy."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "noup@example.com", "password": "alllowercase1!"},
    )
    assert resp.status_code == 400
    assert "uppercase" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_no_digit_rejected(async_client: AsyncClient) -> None:
    """Password missing digit should be rejected by policy."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "nodigit@example.com", "password": "NoDigitHere!!"},
    )
    assert resp.status_code == 400
    assert "digit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_no_special_rejected(async_client: AsyncClient) -> None:
    """Password missing special character should be rejected by policy."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "nospec@example.com", "password": "NoSpecial123"},
    )
    assert resp.status_code == 400
    assert "special" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_strong_password_accepted(async_client: AsyncClient) -> None:
    """A password meeting all complexity rules should succeed."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "strong@example.com", "password": "Str0ng!Pass99"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "strong@example.com"


@pytest.mark.asyncio
async def test_password_reset_weak_password_rejected(async_client: AsyncClient) -> None:
    """Password reset should also enforce complexity rules."""
    # Register a user first
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "resettest@example.com", "password": "Str0ng!Pass99"},
    )
    assert reg.status_code == 200

    # Request password reset
    reset_req = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "resettest@example.com"},
    )
    assert reset_req.status_code == 200
    reset_token = reset_req.json().get("reset_token")
    assert reset_token is not None

    # Try to confirm with weak password (meets min_length but no uppercase/digit/special)
    confirm = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "weakpasswd"},
    )
    assert confirm.status_code == 400
    detail = confirm.json()["detail"].lower()
    assert "uppercase" in detail


@pytest.mark.asyncio
async def test_password_reset_no_special_rejected(async_client: AsyncClient) -> None:
    """Password reset with no special char should be rejected by policy."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "resetspec@example.com", "password": "Str0ng!Pass99"},
    )
    assert reg.status_code == 200

    reset_req = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "resetspec@example.com"},
    )
    assert reset_req.status_code == 200
    reset_token = reset_req.json().get("reset_token")
    assert reset_token is not None

    confirm = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "NoSpecial123"},
    )
    assert confirm.status_code == 400
    assert "special" in confirm.json()["detail"].lower()


@pytest.mark.asyncio
async def test_password_policy_endpoint_returns_rules(async_client: AsyncClient) -> None:
    """GET /auth/password-policy should return current policy config."""
    resp = await async_client.get("/api/v1/auth/password-policy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_length"] == 10
    assert data["require_uppercase"] is True
    assert data["require_lowercase"] is True
    assert data["require_digit"] is True
    assert data["require_special"] is True
