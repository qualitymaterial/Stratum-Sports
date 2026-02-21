"""Integration tests for billing endpoints.

Stripe API calls are patched with unittest.mock so these tests run without
real credentials and without network access.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import User
from app.core.security import get_password_hash


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _register_and_login(async_client: AsyncClient) -> tuple[str, str]:
    """Register a fresh user and return (email, token)."""
    email = "billing-test@example.com"
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "BillingPass1!"},
    )
    assert resp.status_code == 200, resp.text
    return email, resp.json()["access_token"]


# ---------------------------------------------------------------------------
# checkout session
# ---------------------------------------------------------------------------

async def test_checkout_session_without_stripe_config(async_client: AsyncClient):
    """Returns 503 when STRIPE_SECRET_KEY is empty (default in testing)."""
    _, token = await _register_and_login(async_client)
    resp = await async_client.post(
        "/api/v1/billing/create-checkout-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


async def test_checkout_session_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/api/v1/billing/create-checkout-session")
    assert resp.status_code == 401


async def test_checkout_session_with_stripe_mocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Returns a Stripe checkout URL when Stripe is properly mocked."""
    _, token = await _register_and_login(async_client)

    fake_customer = {"id": "cus_test123"}
    fake_session = {"url": "https://checkout.stripe.com/test_session"}

    with (
        patch("app.services.stripe_service.settings") as mock_settings,
        patch("stripe.Customer.create", return_value=fake_customer),
        patch("stripe.checkout.Session.create", return_value=fake_session),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_pro_price_id = "price_test"
        mock_settings.stripe_success_url = "http://localhost:3000/success"
        mock_settings.stripe_cancel_url = "http://localhost:3000/cancel"

        resp = await async_client.post(
            "/api/v1/billing/create-checkout-session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["url"] == "https://checkout.stripe.com/test_session"


# ---------------------------------------------------------------------------
# customer portal
# ---------------------------------------------------------------------------

async def test_portal_without_stripe_config(async_client: AsyncClient):
    """Returns 400 when user has no Stripe customer ID."""
    _, token = await _register_and_login(async_client)
    with patch("app.services.stripe_service.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        resp = await async_client.post(
            "/api/v1/billing/portal",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400
    assert "customer" in resp.json()["detail"].lower()


async def test_portal_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/api/v1/billing/portal")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------

async def test_webhook_rejects_missing_signature(async_client: AsyncClient):
    """Webhook returns 400 when Stripe is configured but no signature is sent."""
    with patch("app.services.stripe_service.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_fake"
        mock_settings.app_env = "production"
        resp = await async_client.post(
            "/api/v1/billing/webhook",
            content=b'{"type":"test"}',
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400


async def test_webhook_checkout_completed(async_client: AsyncClient, db_session: AsyncSession):
    """checkout.session.completed sets stripe_customer_id on the user."""
    email, token = await _register_and_login(async_client)

    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = me_resp.json()["id"]

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": user_id,
                "customer": "cus_webhook_test",
            }
        },
    }

    with patch("app.services.stripe_service.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""
        mock_settings.app_env = "development"

        with patch("stripe.Webhook.construct_event"):
            resp = await async_client.post(
                "/api/v1/billing/webhook",
                json=fake_event,
                headers={"Content-Type": "application/json"},
            )

    assert resp.status_code == 200
    assert resp.json()["type"] == "checkout.session.completed"
