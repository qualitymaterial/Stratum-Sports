from datetime import UTC, datetime
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.models.password_reset_token import PasswordResetToken
from app.models.subscription import Subscription
from app.models.user import User
from app.models.teaser_interaction_event import TeaserInteractionEvent

STEP_UP_PASSWORD = "AdminRoutePass123!"
CONFIRM_PHRASE = "CONFIRM"


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


async def _ensure_password_reset_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: PasswordResetToken.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


def _make_subscription(
    *,
    user: User,
    stripe_subscription_id: str,
    status: str = "active",
    cancel_at_period_end: bool = False,
) -> Subscription:
    return Subscription(
        user_id=user.id,
        stripe_customer_id=user.stripe_customer_id or "cus_test_default",
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id="price_test_pro",
        status=status,
        current_period_end=datetime(2026, 12, 31, tzinfo=UTC),
        cancel_at_period_end=cancel_at_period_end,
    )


def _mutation_security_fields(
    *,
    password: str = STEP_UP_PASSWORD,
    confirm_phrase: str = CONFIRM_PHRASE,
) -> dict[str, str]:
    return {
        "step_up_password": password,
        "confirm_phrase": confirm_phrase,
    }


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
        json={
            "tier": "pro",
            "reason": "Billing role should not modify tiers",
            **_mutation_security_fields(),
        },
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
        json={
            "tier": "pro",
            "reason": "Support upgrade after subscription verification",
            **_mutation_security_fields(),
        },
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
        json={"tier": "pro", "reason": "short", **_mutation_security_fields()},
    )
    assert response.status_code == 422


async def test_admin_update_user_tier_requires_step_up_password(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-tier-stepup@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-tier-stepup@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "ops_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-tier-stepup-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-tier-stepup-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tier": "pro",
            "reason": "Tier change requires step-up verification",
            **_mutation_security_fields(password="WrongPass123!"),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Step-up authentication failed"


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
        json={
            "admin_role": "support_admin",
            "reason": "Ops should not assign admin roles",
            **_mutation_security_fields(),
        },
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
        json={
            "admin_role": "support_admin",
            "reason": "Assign support access for customer operations",
            **_mutation_security_fields(),
        },
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


async def test_admin_update_user_role_requires_confirm_phrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-role-confirm@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-role-confirm@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "super_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-role-confirm-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-role-confirm-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "admin_role": "support_admin",
            "reason": "Role change requires explicit confirmation phrase",
            **_mutation_security_fields(confirm_phrase="APPROVE"),
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Confirmation phrase must be 'CONFIRM'"


async def test_admin_update_user_active_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-active-support@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-active-support@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-active-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-active-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/active",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-active-update"},
        json={
            "is_active": False,
            "reason": "Deactivate account for security review",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["old_is_active"] is True
    assert payload["new_is_active"] is False

    refreshed_target = await db_session.get(User, target_user.id)
    assert refreshed_target is not None
    assert refreshed_target.is_active is False

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.user.active.update",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Deactivate account for security review"
    assert audit_row.before_payload == {"is_active": True}
    assert audit_row.after_payload == {"is_active": False}
    assert audit_row.request_id == "test-active-update"


async def test_admin_update_user_active_requires_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-active-billing@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-active-billing@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-active-perm-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-active-perm-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/active",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "is_active": False,
            "reason": "Billing role should not deactivate accounts",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_password_reset_request_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    await _ensure_password_reset_table(db_session)
    token = await _register(async_client, "admin-reset-support@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-reset-support@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-reset-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-reset-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/password-reset",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-admin-reset"},
        json={
            "reason": "Support-assisted password reset request",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["email"] == "admin-reset-target@example.com"
    assert payload["message"] == "Password reset requested successfully"

    token_stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == target_user.id)
    token_row = (await db_session.execute(token_stmt)).scalars().first()
    assert token_row is not None
    assert token_row.used_at is None

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.user.password_reset.request",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Support-assisted password reset request"
    assert audit_row.request_id == "test-admin-reset"


async def test_admin_user_billing_overview_returns_subscription(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-billing-overview-support@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-overview-support@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-overview-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-overview-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_overview_target"
    db_session.add(
        _make_subscription(
            user=target_user,
            stripe_subscription_id="sub_overview_target",
            status="active",
            cancel_at_period_end=False,
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/admin/users/{target_user.id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user_id"] == str(target_user.id)
    assert payload["stripe_customer_id"] == "cus_overview_target"
    assert payload["subscription"] is not None
    assert payload["subscription"]["stripe_subscription_id"] == "sub_overview_target"
    assert payload["subscription"]["status"] == "active"


async def test_admin_user_billing_resync_requires_billing_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-billing-resync-support@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-resync-support@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-resync-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-resync-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_resync_target"
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/billing/resync",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "reason": "Support role should not mutate billing state",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_user_billing_resync_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-billing-resync-admin@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-resync-admin@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-resync-target-2@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-resync-target-2@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_resync_target_2"
    target_user.tier = "free"
    await db_session.commit()

    with (
        patch("app.services.stripe_service.settings") as mock_settings,
        patch(
            "stripe.Subscription.list",
            return_value={
                "data": [
                    {
                        "id": "sub_resync_latest",
                        "created": 200,
                        "status": "active",
                        "cancel_at_period_end": False,
                        "current_period_end": 1_900_000_000,
                        "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
                    }
                ]
            },
        ),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_pro_price_id = "price_default"
        response = await async_client.post(
            f"/api/v1/admin/users/{target_user.id}/billing/resync",
            headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-billing-resync"},
            json={
                "reason": "Billing reconciliation after partner ticket",
                **_mutation_security_fields(),
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "resync"
    assert payload["new_status"] == "active"
    assert payload["new_cancel_at_period_end"] is False
    assert payload["subscription_id"] == "sub_resync_latest"

    await db_session.refresh(target_user)
    assert target_user.tier == "pro"

    subscription_stmt = (
        select(Subscription)
        .where(Subscription.user_id == target_user.id)
        .order_by(Subscription.updated_at.desc())
        .limit(1)
    )
    subscription = (await db_session.execute(subscription_stmt)).scalar_one()
    assert subscription.status == "active"
    assert subscription.cancel_at_period_end is False
    assert subscription.stripe_subscription_id == "sub_resync_latest"

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.billing.resync",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Billing reconciliation after partner ticket"
    assert audit_row.request_id == "test-billing-resync"


async def test_admin_user_billing_cancel_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-billing-cancel@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-billing-cancel@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-cancel-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-cancel-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_cancel_target"
    target_user.tier = "pro"
    db_session.add(
        _make_subscription(
            user=target_user,
            stripe_subscription_id="sub_cancel_target",
            status="active",
            cancel_at_period_end=False,
        )
    )
    await db_session.commit()

    with (
        patch("app.services.stripe_service.settings") as mock_settings,
        patch(
            "stripe.Subscription.modify",
            return_value={
                "id": "sub_cancel_target",
                "status": "active",
                "cancel_at_period_end": True,
                "current_period_end": 1_900_000_000,
                "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
            },
        ),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_pro_price_id = "price_default"
        response = await async_client.post(
            f"/api/v1/admin/users/{target_user.id}/billing/cancel",
            headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-billing-cancel"},
            json={
                "reason": "Customer requested cancellation at period end",
                **_mutation_security_fields(),
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "cancel"
    assert payload["previous_cancel_at_period_end"] is False
    assert payload["new_cancel_at_period_end"] is True
    assert payload["subscription_id"] == "sub_cancel_target"

    subscription_stmt = select(Subscription).where(
        Subscription.user_id == target_user.id,
        Subscription.stripe_subscription_id == "sub_cancel_target",
    )
    subscription = (await db_session.execute(subscription_stmt)).scalar_one()
    assert subscription.cancel_at_period_end is True

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.billing.cancel",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Customer requested cancellation at period end"
    assert audit_row.request_id == "test-billing-cancel"


async def test_admin_user_billing_reactivate_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    token = await _register(async_client, "admin-billing-reactivate@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-reactivate@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-reactivate-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-reactivate-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_reactivate_target"
    target_user.tier = "pro"
    db_session.add(
        _make_subscription(
            user=target_user,
            stripe_subscription_id="sub_reactivate_target",
            status="active",
            cancel_at_period_end=True,
        )
    )
    await db_session.commit()

    with (
        patch("app.services.stripe_service.settings") as mock_settings,
        patch(
            "stripe.Subscription.modify",
            return_value={
                "id": "sub_reactivate_target",
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": 1_900_000_000,
                "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
            },
        ),
    ):
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_pro_price_id = "price_default"
        response = await async_client.post(
            f"/api/v1/admin/users/{target_user.id}/billing/reactivate",
            headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-billing-reactivate"},
            json={
                "reason": "Customer reversed cancellation request",
                **_mutation_security_fields(),
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "reactivate"
    assert payload["previous_cancel_at_period_end"] is True
    assert payload["new_cancel_at_period_end"] is False
    assert payload["subscription_id"] == "sub_reactivate_target"

    subscription_stmt = select(Subscription).where(
        Subscription.user_id == target_user.id,
        Subscription.stripe_subscription_id == "sub_reactivate_target",
    )
    subscription = (await db_session.execute(subscription_stmt)).scalar_one()
    assert subscription.cancel_at_period_end is False

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.target_id == str(target_user.id),
        AdminAuditLog.action_type == "admin.billing.reactivate",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.reason == "Customer reversed cancellation request"
    assert audit_row.request_id == "test-billing-reactivate"


async def test_admin_user_billing_mutation_requires_step_up_password(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-billing-stepup@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-billing-stepup@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-stepup-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-stepup-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = "cus_stepup_target"
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/billing/resync",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "reason": "Billing operations require step-up authentication",
            **_mutation_security_fields(password="WrongPass123!"),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Step-up authentication failed"


async def test_admin_user_billing_resync_requires_stripe_customer_id(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-billing-no-customer@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-no-customer@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-billing-no-customer-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-billing-no-customer-target@example.com"))
    ).scalar_one()
    target_user.stripe_customer_id = None
    await db_session.commit()

    with patch("app.services.stripe_service.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        response = await async_client.post(
            f"/api/v1/admin/users/{target_user.id}/billing/resync",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "reason": "Attempt resync without Stripe customer should fail",
                **_mutation_security_fields(),
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "User has no Stripe customer ID"


async def test_admin_user_search_requires_admin(
    async_client: AsyncClient,
) -> None:
    token = await _register(async_client, "admin-user-search-free@example.com")
    response = await async_client.get(
        "/api/v1/admin/users?q=admin-user-search-free",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_user_search_returns_matches(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-user-search-admin@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-user-search-admin@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-user-search-target@example.com")
    await _register(async_client, "admin-user-search-target-two@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-user-search-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    email_resp = await async_client.get(
        "/api/v1/admin/users?q=admin-user-search-target&limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert email_resp.status_code == 200, email_resp.text
    email_payload = email_resp.json()
    assert email_payload["limit"] == 5
    assert email_payload["total"] >= 1
    assert any(row["email"] == "admin-user-search-target@example.com" for row in email_payload["items"])

    uuid_fragment = str(target_user.id).split("-")[0]
    uuid_resp = await async_client.get(
        f"/api/v1/admin/users?q={uuid_fragment}&limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uuid_resp.status_code == 200, uuid_resp.text
    uuid_payload = uuid_resp.json()
    assert uuid_payload["limit"] == 1
    assert len(uuid_payload["items"]) <= 1
    assert any(row["id"] == str(target_user.id) for row in uuid_payload["items"])


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
        json={
            "admin_role": "support_admin",
            "reason": "Role assignment for test coverage",
            **_mutation_security_fields(),
        },
    )
    assert role_resp.status_code == 200

    tier_resp = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/tier",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tier": "pro",
            "reason": "Tier update for test coverage",
            **_mutation_security_fields(),
        },
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
