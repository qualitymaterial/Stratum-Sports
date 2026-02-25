from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.api_partner_key import ApiPartnerKey
from app.models.clv_record import ClvRecord
from app.models.cycle_kpi import CycleKpi
from app.models.game import Game
from app.models.password_reset_token import PasswordResetToken
from app.models.signal import Signal
from app.models.subscription import Subscription
from app.models.teaser_interaction_event import TeaserInteractionEvent
from app.models.user import User
from app.services.partner_api_keys import hash_partner_api_key

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


async def _ensure_api_partner_keys_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: ApiPartnerKey.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


async def _ensure_api_partner_entitlements_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: ApiPartnerEntitlement.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


async def _ensure_outcomes_tables(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: Game.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )
    await db_session.run_sync(
        lambda sync_session: Signal.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )
    await db_session.run_sync(
        lambda sync_session: ClvRecord.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )
    await db_session.run_sync(
        lambda sync_session: CycleKpi.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


async def _seed_outcomes_dataset(
    db_session: AsyncSession,
    *,
    now: datetime,
    suffix: str,
) -> None:
    game_nba = Game(
        event_id=f"evt-outcomes-nba-{suffix}",
        sport_key="basketball_nba",
        commence_time=now + timedelta(hours=4),
        home_team="Home Team",
        away_team="Away Team",
    )
    game_nfl = Game(
        event_id=f"evt-outcomes-nfl-{suffix}",
        sport_key="americanfootball_nfl",
        commence_time=now + timedelta(hours=30),
        home_team="Home Football",
        away_team="Away Football",
    )
    db_session.add_all([game_nba, game_nfl])
    await db_session.flush()

    signal_a = Signal(
        event_id=game_nba.event_id,
        market="spreads",
        signal_type="MOVE",
        direction="UP",
        from_value=-2.0,
        to_value=-1.5,
        from_price=-110,
        to_price=-108,
        window_minutes=30,
        books_affected=4,
        velocity_minutes=0.2,
        time_bucket="PRETIP",
        strength_score=78,
        created_at=now - timedelta(minutes=1),
        metadata_json={"outcome_name": "Away Team"},
    )
    signal_b = Signal(
        event_id=game_nba.event_id,
        market="totals",
        signal_type="KEY_CROSS",
        direction="UP",
        from_value=220.5,
        to_value=221.0,
        from_price=-112,
        to_price=-105,
        window_minutes=30,
        books_affected=5,
        velocity_minutes=0.15,
        time_bucket="LATE",
        strength_score=72,
        created_at=now - timedelta(minutes=2),
        metadata_json={"outcome_name": "Over"},
    )
    signal_c = Signal(
        event_id=game_nfl.event_id,
        market="h2h",
        signal_type="MOVE",
        direction="UP",
        from_value=-120,
        to_value=-118,
        from_price=-120,
        to_price=-118,
        window_minutes=60,
        books_affected=3,
        velocity_minutes=0.1,
        time_bucket="OPEN",
        strength_score=65,
        created_at=now - timedelta(minutes=20),
        metadata_json={"outcome_name": "Home Football"},
    )
    db_session.add_all([signal_a, signal_b, signal_c])
    await db_session.flush()

    db_session.add_all(
        [
            ClvRecord(
                signal_id=signal_a.id,
                event_id=signal_a.event_id,
                signal_type=signal_a.signal_type,
                market=signal_a.market,
                outcome_name="Away Team",
                entry_line=-1.5,
                close_line=-1.0,
                clv_line=0.5,
                clv_prob=0.02,
                computed_at=now - timedelta(hours=2),
            ),
            ClvRecord(
                signal_id=signal_b.id,
                event_id=signal_b.event_id,
                signal_type=signal_b.signal_type,
                market=signal_b.market,
                outcome_name="Over",
                entry_line=221.0,
                close_line=221.5,
                clv_line=-0.05,
                clv_prob=0.01,
                computed_at=now - timedelta(hours=3),
            ),
            ClvRecord(
                signal_id=signal_c.id,
                event_id=signal_c.event_id,
                signal_type=signal_c.signal_type,
                market=signal_c.market,
                outcome_name="Home Football",
                entry_price=-118,
                close_price=-125,
                clv_line=-0.4,
                clv_prob=-0.03,
                computed_at=now - timedelta(hours=4),
            ),
        ]
    )

    db_session.add_all(
        [
            CycleKpi(
                cycle_id=f"cycle-outcomes-1-{suffix}",
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(minutes=59),
                duration_ms=60_000,
                degraded=False,
                alerts_sent=6,
                alerts_failed=1,
                signals_created_total=8,
            ),
            CycleKpi(
                cycle_id=f"cycle-outcomes-2-{suffix}",
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=1, minutes=59),
                duration_ms=62_000,
                degraded=True,
                alerts_sent=3,
                alerts_failed=2,
                signals_created_total=5,
            ),
        ]
    )
    await db_session.commit()


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


async def test_admin_outcomes_report_requires_admin_read(
    async_client: AsyncClient,
) -> None:
    token = await _register(async_client, "admin-outcomes-free@example.com")
    response = await async_client.get(
        "/api/v1/admin/outcomes/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_outcomes_exports_require_admin_read(
    async_client: AsyncClient,
) -> None:
    token = await _register(async_client, "admin-outcomes-export-free@example.com")
    json_response = await async_client.get(
        "/api/v1/admin/outcomes/export.json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert json_response.status_code == 403
    assert json_response.json()["detail"] == "Insufficient admin permissions"

    csv_response = await async_client.get(
        "/api/v1/admin/outcomes/export.csv?table=summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert csv_response.status_code == 403
    assert csv_response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_outcomes_report_returns_clv_kpis_and_baseline_status(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_outcomes_tables(db_session)
    token = await _register(async_client, "admin-outcomes-reader@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-outcomes-reader@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"
    await db_session.commit()
    await _seed_outcomes_dataset(db_session, now=datetime.now(UTC), suffix="reader")

    response = await async_client.get(
        "/api/v1/admin/outcomes/report?days=30&baseline_days=14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kpis"]["clv_samples"] == 3
    assert payload["kpis"]["positive_count"] == 2
    assert payload["kpis"]["negative_count"] == 1
    assert payload["status"] == "baseline_building"
    assert "Collecting CLV samples" in payload["status_reason"]
    assert isinstance(payload["by_signal_type"], list)
    assert isinstance(payload["by_market"], list)
    assert isinstance(payload["top_filtered_reasons"], list)


async def test_admin_outcomes_report_filter_propagation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_outcomes_tables(db_session)
    token = await _register(async_client, "admin-outcomes-filter@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-outcomes-filter@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "ops_admin"
    admin_user.tier = "pro"
    await db_session.commit()
    await _seed_outcomes_dataset(db_session, now=datetime.now(UTC), suffix="filter")

    response = await async_client.get(
        "/api/v1/admin/outcomes/report"
        "?days=30&baseline_days=14&sport_key=basketball_nba&signal_type=MOVE&market=spreads&time_bucket=PRETIP",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kpis"]["clv_samples"] == 1
    assert payload["kpis"]["positive_count"] == 1
    assert payload["by_signal_type"] == [
        {
            "name": "MOVE",
            "count": 1,
            "positive_rate": 1.0,
            "avg_clv_line": 0.5,
            "avg_clv_prob": 0.02,
        }
    ]
    assert payload["by_market"] == [
        {
            "name": "spreads",
            "count": 1,
            "positive_rate": 1.0,
            "avg_clv_line": 0.5,
            "avg_clv_prob": 0.02,
        }
    ]


async def test_admin_outcomes_json_export_attachment_headers(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_outcomes_tables(db_session)
    token = await _register(async_client, "admin-outcomes-json@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-outcomes-json@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"
    await db_session.commit()
    await _seed_outcomes_dataset(db_session, now=datetime.now(UTC), suffix="json")

    response = await async_client.get(
        "/api/v1/admin/outcomes/export.json?days=30&baseline_days=14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment; filename=\"admin-outcomes-report-" in response.headers["content-disposition"]
    payload = response.json()
    assert "kpis" in payload
    assert "baseline_kpis" in payload
    assert "delta_vs_baseline" in payload


async def test_admin_outcomes_csv_export_summary_and_breakdown_headers(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_outcomes_tables(db_session)
    token = await _register(async_client, "admin-outcomes-csv@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-outcomes-csv@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"
    await db_session.commit()
    await _seed_outcomes_dataset(db_session, now=datetime.now(UTC), suffix="csv")

    summary_response = await async_client.get(
        "/api/v1/admin/outcomes/export.csv?table=summary&days=30&baseline_days=14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary_response.status_code == 200, summary_response.text
    assert summary_response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"admin-outcomes-summary-" in summary_response.headers["content-disposition"]
    summary_lines = summary_response.text.strip().splitlines()
    assert summary_lines[0] == "metric,current,baseline,delta"
    assert summary_lines[1].startswith("clv_samples,")

    market_response = await async_client.get(
        "/api/v1/admin/outcomes/export.csv?table=by_market&days=30&baseline_days=14",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert market_response.status_code == 200, market_response.text
    market_lines = market_response.text.strip().splitlines()
    assert market_lines[0] == "market,count,positive_rate,avg_clv_line,avg_clv_prob"


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


async def test_admin_issue_partner_key_requires_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_api_partner_keys_table(db_session)
    token = await _register(async_client, "admin-partner-support@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-partner-support@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-partner-target@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-partner-target@example.com"))).scalar_one()
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Primary Partner Key",
            "expires_in_days": 90,
            "reason": "Support role should not issue partner keys",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_update_partner_entitlement_requires_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_api_partner_entitlements_table(db_session)
    token = await _register(async_client, "admin-entitlement-support@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-support@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "support_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-entitlement-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/api-entitlement",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "plan_code": "api_monthly",
            "api_access_enabled": True,
            "soft_limit_monthly": 10000,
            "reason": "Support role should not modify partner entitlement",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient admin permissions"


async def test_admin_get_partner_entitlement_defaults_when_missing(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_api_partner_entitlements_table(db_session)
    token = await _register(async_client, "admin-entitlement-read@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-read@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-entitlement-read-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-read-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/admin/users/{target_user.id}/api-entitlement",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user_id"] == str(target_user.id)
    assert payload["entitlement_id"] is None
    assert payload["plan_code"] is None
    assert payload["api_access_enabled"] is False
    assert payload["soft_limit_monthly"] is None
    assert payload["overage_enabled"] is True
    assert payload["overage_price_cents"] is None
    assert payload["overage_unit_quantity"] == 1000


async def test_admin_update_partner_entitlement_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    await _ensure_api_partner_entitlements_table(db_session)
    token = await _register(async_client, "admin-entitlement-write@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-write@example.com"))
    ).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-entitlement-write-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-entitlement-write-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/admin/users/{target_user.id}/api-entitlement",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-partner-entitlement-update"},
        json={
            "plan_code": "api_monthly",
            "api_access_enabled": True,
            "soft_limit_monthly": 25000,
            "overage_enabled": True,
            "overage_price_cents": 299,
            "overage_unit_quantity": 1000,
            "reason": "Enable paid API partner plan with default overage policy",
            **_mutation_security_fields(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["new_entitlement"]["plan_code"] == "api_monthly"
    assert payload["new_entitlement"]["api_access_enabled"] is True
    assert payload["new_entitlement"]["soft_limit_monthly"] == 25000
    assert payload["new_entitlement"]["overage_enabled"] is True
    assert payload["new_entitlement"]["overage_price_cents"] == 299
    assert payload["new_entitlement"]["overage_unit_quantity"] == 1000

    ent_stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == target_user.id)
    ent_row = (await db_session.execute(ent_stmt)).scalar_one()
    assert ent_row.plan_code == "api_monthly"
    assert ent_row.api_access_enabled is True
    assert ent_row.soft_limit_monthly == 25000
    assert ent_row.overage_enabled is True
    assert ent_row.overage_price_cents == 299
    assert ent_row.overage_unit_quantity == 1000

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.action_type == "admin.partner_entitlement.update",
        AdminAuditLog.target_id == str(target_user.id),
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.request_id == "test-partner-entitlement-update"


async def test_admin_issue_partner_key_and_list_keys(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    await _ensure_api_partner_keys_table(db_session)
    token = await _register(async_client, "admin-partner-billing@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-partner-billing@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-partner-target-2@example.com")
    target_user = (await db_session.execute(select(User).where(User.email == "admin-partner-target-2@example.com"))).scalar_one()
    await db_session.commit()

    issue_response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-partner-key-issue"},
        json={
            "name": "Primary Partner Key",
            "expires_in_days": 90,
            "reason": "Create partner key for private feed integration",
            **_mutation_security_fields(),
        },
    )
    assert issue_response.status_code == 200, issue_response.text
    issue_payload = issue_response.json()
    assert issue_payload["operation"] == "issue"
    assert issue_payload["key"]["name"] == "Primary Partner Key"
    assert issue_payload["api_key"].startswith("stratum_pk_")

    key_stmt = select(ApiPartnerKey).where(ApiPartnerKey.id == issue_payload["key"]["id"])
    key_row = (await db_session.execute(key_stmt)).scalar_one()
    assert key_row.key_prefix == issue_payload["api_key"][:16]
    assert key_row.key_hash == hash_partner_api_key(issue_payload["api_key"])
    assert key_row.is_active is True

    list_response = await async_client.get(
        f"/api/v1/admin/users/{target_user.id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total_keys"] == 1
    assert list_payload["active_keys"] == 1
    assert list_payload["items"][0]["key_prefix"] == key_row.key_prefix

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.action_type == "admin.partner_api_key.issue",
        AdminAuditLog.target_id == str(target_user.id),
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.request_id == "test-partner-key-issue"


async def test_admin_revoke_partner_key_writes_audit_log(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    await _ensure_api_partner_keys_table(db_session)
    token = await _register(async_client, "admin-partner-revoke@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-partner-revoke@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-partner-revoke-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-partner-revoke-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    issue_response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Revoke Test Key",
            "expires_in_days": 30,
            "reason": "Issue key before revoke test",
            **_mutation_security_fields(),
        },
    )
    key_id = issue_response.json()["key"]["id"]

    revoke_response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys/{key_id}/revoke",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-partner-key-revoke"},
        json={
            "reason": "Credential rotation after integration changes",
            **_mutation_security_fields(),
        },
    )
    assert revoke_response.status_code == 200, revoke_response.text
    revoke_payload = revoke_response.json()
    assert revoke_payload["operation"] == "revoke"
    assert revoke_payload["old_is_active"] is True
    assert revoke_payload["new_is_active"] is False
    assert revoke_payload["revoked_at"] is not None

    key_stmt = select(ApiPartnerKey).where(ApiPartnerKey.id == key_id)
    key_row = (await db_session.execute(key_stmt)).scalar_one()
    assert key_row.is_active is False
    assert key_row.revoked_at is not None

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.action_type == "admin.partner_api_key.revoke",
        AdminAuditLog.target_id == key_id,
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.request_id == "test-partner-key-revoke"


async def test_admin_rotate_partner_key_creates_new_active_key(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_admin_audit_table(db_session)
    await _ensure_api_partner_keys_table(db_session)
    token = await _register(async_client, "admin-partner-rotate@example.com")
    admin_user = (await db_session.execute(select(User).where(User.email == "admin-partner-rotate@example.com"))).scalar_one()
    admin_user.is_admin = False
    admin_user.admin_role = "billing_admin"
    admin_user.tier = "pro"

    await _register(async_client, "admin-partner-rotate-target@example.com")
    target_user = (
        await db_session.execute(select(User).where(User.email == "admin-partner-rotate-target@example.com"))
    ).scalar_one()
    await db_session.commit()

    issue_response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Rotate Seed Key",
            "expires_in_days": 60,
            "reason": "Issue key before rotate test",
            **_mutation_security_fields(),
        },
    )
    original_key_id = issue_response.json()["key"]["id"]

    rotate_response = await async_client.post(
        f"/api/v1/admin/users/{target_user.id}/api-keys/{original_key_id}/rotate",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-partner-key-rotate"},
        json={
            "name": "Rotated Key",
            "expires_in_days": 120,
            "reason": "Rotate key after partner security request",
            **_mutation_security_fields(),
        },
    )
    assert rotate_response.status_code == 200, rotate_response.text
    rotate_payload = rotate_response.json()
    assert rotate_payload["operation"] == "rotate"
    assert rotate_payload["api_key"].startswith("stratum_pk_")
    assert rotate_payload["key"]["name"] == "Rotated Key"
    assert rotate_payload["key"]["id"] != original_key_id

    keys_stmt = select(ApiPartnerKey).where(ApiPartnerKey.user_id == target_user.id)
    key_rows = list((await db_session.execute(keys_stmt)).scalars().all())
    assert len(key_rows) == 2
    assert sum(1 for key in key_rows if key.is_active) == 1
    assert any(str(key.id) == original_key_id and not key.is_active for key in key_rows)

    audit_stmt = select(AdminAuditLog).where(
        AdminAuditLog.action_type == "admin.partner_api_key.rotate",
        AdminAuditLog.request_id == "test-partner-key-rotate",
    )
    audit_row = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_row.actor_user_id == admin_user.id


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
