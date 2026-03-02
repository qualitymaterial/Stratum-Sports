from httpx import AsyncClient


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "WebhookPass1!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_partner_webhook_create_rejects_non_https(async_client: AsyncClient) -> None:
    token = await _register(async_client, "partner-webhook-http@example.com")
    response = await async_client.post(
        "/api/v1/partner/webhooks",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "http://partner.example.com/hook", "description": "bad scheme"},
    )
    assert response.status_code == 422
    assert "https" in response.json()["detail"].lower()


async def test_partner_webhook_create_rejects_private_ip(async_client: AsyncClient) -> None:
    token = await _register(async_client, "partner-webhook-private@example.com")
    response = await async_client.post(
        "/api/v1/partner/webhooks",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://127.0.0.1/hook", "description": "private ip"},
    )
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"].lower()


async def test_partner_webhook_update_rejects_localhost(async_client: AsyncClient) -> None:
    token = await _register(async_client, "partner-webhook-update@example.com")
    create_response = await async_client.post(
        "/api/v1/partner/webhooks",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://partner.example.com/hook", "description": "valid"},
    )
    assert create_response.status_code == 200, create_response.text
    webhook_id = create_response.json()["id"]

    update_response = await async_client.patch(
        f"/api/v1/partner/webhooks/{webhook_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://localhost/hook"},
    )
    assert update_response.status_code == 422
    assert "not allowed" in update_response.json()["detail"].lower()
