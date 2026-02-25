from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User
from app.models.teaser_interaction_event import TeaserInteractionEvent


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AdminRoutePass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _ensure_teaser_events_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: TeaserInteractionEvent.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


async def _ensure_admin_audit_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: AdminAuditLog.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


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
    assert "conversion" in payload
    assert payload["report"]["days"] == 7


async def test_admin_conversion_funnel_includes_teaser_interactions(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_teaser_events_table(db_session)
    token = await _register(async_client, "admin-conversion@example.com")
    user = (await db_session.execute(select(User).where(User.email == "admin-conversion@example.com"))).scalar_one()
    user.is_admin = True
    user.tier = "pro"
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    view_resp = await async_client.post(
        "/api/v1/intel/teaser/events",
        headers=headers,
        json={"event_name": "viewed_teaser", "source": "performance_page", "sport_key": "basketball_nba"},
    )
    assert view_resp.status_code == 200

    click_resp = await async_client.post(
        "/api/v1/intel/teaser/events",
        headers=headers,
        json={"event_name": "clicked_upgrade_from_teaser", "source": "free_delayed_opportunities", "sport_key": "basketball_nba"},
    )
    assert click_resp.status_code == 200

    response = await async_client.get(
        "/api/v1/admin/conversion/funnel?days=7",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["teaser_views"] >= 1
    assert payload["teaser_clicks"] >= 1
    assert isinstance(payload["by_sport"], list)
    assert any(row["sport_key"] == "basketball_nba" for row in payload["by_sport"])


async def test_admin_update_user_tier_requires_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-tier-billing@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-tier-billing@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-tier-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-tier-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}"},
        json={"tier": "pro", "reason": "Billing role should not modify tiers"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_update_user_tier_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-tier-ops@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-tier-ops@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "ops_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-tier-target-2@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-tier-target-2@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-tier-update"},
        json={"tier": "pro", "reason": "Support upgrade after subscription verification"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["old_tier"] == "free"
    assert payload["new_tier"] == "pro"
    assert payload["reason"] == "Support upgrade after subscription verification"

    refreshed_target = await db_session.get(User, target_user.id)
    assert refreshed_target is not None
    assert refreshed_target.tier == "pro"

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.user.tier.update",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Support upgrade after subscription verification"
    assert audit_row.before_payload == {"tier": "free"}
    assert audit_row.after_payload == {"tier": "pro"}
    assert audit_row.request_id == "test-tier-update"


async def test_admin_update_user_tier_requires_reason(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-tier-short-reason@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-tier-short-reason@example.com"))
    ).scalar_one()
    admin_user.is_admin = True
    admin_user.tier = "pro"

    await _register(async_client, "admin-tier-target-3@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-tier-target-3@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}"},
        json={"tier": "pro", "reason": "short"},
    )
    assert response.status_code == 422
