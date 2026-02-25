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


async def test_admin_update_user_role_requires_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-role-ops@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-role-ops@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "ops_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-role-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-role-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"admin_role": "support_admin", "reason": "Ops should not assign admin roles"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_update_user_role_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-role-super@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-role-super@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "super_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-role-target-2@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-role-target-2@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-role-update"},
        json={"admin_role": "support_admin", "reason": "Assign support access for customer operations"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["old_admin_role"] is None
    assert payload["new_admin_role"] == "support_admin"
    assert payload["old_is_admin"] is False
    assert payload["new_is_admin"] is True

    refreshed_target = await db_session.get(User, target_user.id)
    assert refreshed_target is not None
    assert refreshed_target.admin_role == "support_admin"
    assert refreshed_target.is_admin is True

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.user.role.update",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Assign support access for customer operations"
    assert audit_row.before_payload == {"admin_role": None, "is_admin": False}
    assert audit_row.after_payload == {"admin_role": "support_admin", "is_admin": True}
    assert audit_row.request_id == "test-role-update"


async def test_admin_audit_logs_filters_and_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-audit-super@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-audit-super@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "super_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-audit-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-audit-target@example.com"))).scalar_one()
    await db_session.commit()

    role_resp = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"admin_role": "support_admin", "reason": "Role assignment for test coverage"},
    )
    assert role_resp.status_code == 200

    tier_resp = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}"},
        json={"tier": "pro", "reason": "Tier update for test coverage"},
    )
    assert tier_resp.status_code == 200

    logs_resp = await async_client.get(
        "/api/v1/admin/audit/logs?action_type=admin.user.role.update&limit=10&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logs_resp.status_code == 200, logs_resp.text
    payload = logs_resp.json()
    assert payload["total"] >= 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert len(payload["items"]) >= 1
    assert all(item["action_type"] == "admin.user.role.update" for item in payload["items"])

    paged_resp = await async_client.get(
        "/api/v1/admin/audit/logs?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert paged_resp.status_code == 200
    paged_payload = paged_resp.json()
    assert paged_payload["limit"] == 1
    assert len(paged_payload["items"]) <= 1
