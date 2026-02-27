"""Tests for Kalshi verification admin endpoints and poller enhancements."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.user import User

# Let's import the same register helper used in other tests or redefine locally
async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AdminRoutePass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _make_admin(db_session: AsyncSession, email: str) -> None:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    user.admin_role = "super_admin"
    user.tier = "pro"
    await db_session.commit()


def _alignment(
    key: str = "cek_admin_test",
    sportsbook_event_id: str = "sb_admin_test_1",
    kalshi_market_id: str | None = "kalshi-test-mkt-1",
) -> CanonicalEventAlignment:
    return CanonicalEventAlignment(
        canonical_event_key=key,
        sport="basketball",
        league="NBA",
        home_team="BOS",
        away_team="NYK",
        start_time=datetime.now(UTC) + timedelta(hours=2),
        sportsbook_event_id=sportsbook_event_id,
        kalshi_market_id=kalshi_market_id,
    )


# ── 1. Admin Exports Tests ──────────────────────────────────────────────────────────

async def test_admin_kalshi_alignments_export(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(_alignment())
    await db_session.commit()

    token = await _register(async_client, "admin-alignments@example.com")
    await _make_admin(db_session, "admin-alignments@example.com")

    response = await async_client.get(
        "/api/v1/admin/kalshi/alignments/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "kalshi-alignments" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0] == "canonical_event_key,sportsbook_event_id,kalshi_market_id,start_time,created_at"
    assert "cek_admin_test" in response.text
    assert "sb_admin_test_1" in response.text


async def test_admin_kalshi_quotes_export(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    db_session.add(ExchangeQuoteEvent(
        canonical_event_key="cek_admin_quote",
        source="KALSHI",
        market_id="kalshi-test-mkt-2",
        outcome_name="YES",
        probability=0.55,
        price=0.55,
        timestamp=now,
    ))
    db_session.add(ExchangeQuoteEvent(
        canonical_event_key="cek_admin_quote_invalid",
        source="KALSHI",
        market_id="kalshi-test-mkt-invalid",
        outcome_name="NO", # should flag invalid mostly because we look for YES
        probability=1.5, # invalid
        price=1.5,
        timestamp=now,
    ))
    await db_session.commit()

    token = await _register(async_client, "admin-quotes@example.com")
    await _make_admin(db_session, "admin-quotes@example.com")

    response = await async_client.get(
        "/api/v1/admin/kalshi/quotes/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert "canonical_event_key,market_id,outcome_name,probability,price,timestamp,created_at,valid,invalid_reason" in lines[0]
    
    # Second line should be valid
    assert "True" in response.text
    # Third line should be invalid
    assert "False" in response.text


async def test_admin_kalshi_debug_view_export(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(_alignment(key="cek_debug", sportsbook_event_id="sb_debug_1"))
    await db_session.commit()

    token = await _register(async_client, "admin-debug@example.com")
    await _make_admin(db_session, "admin-debug@example.com")

    response = await async_client.get(
        "/api/v1/admin/kalshi/debug_view/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    header = lines[0]
    assert "last_structural_event_ts" in header
    assert "last_divergence_resolved" in header
    assert len(lines) >= 2
    assert "cek_debug" in lines[1]


async def test_admin_kalshi_idempotency_audit_export(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(async_client, "admin-audit@example.com")
    await _make_admin(db_session, "admin-audit@example.com")

    response = await async_client.get(
        "/api/v1/admin/kalshi/idempotency_audit/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert "check_name,key_fields,duplicate_count" in lines[0]
    # With unique constraints enforced, no duplicates should exist
    assert len(lines) == 1  # header only


# ── 2. Poller Counters Mock Tests ──────────────────────────────────────────────────────────

async def test_poller_always_returns_counters() -> None:
    from app.tasks.poller import run_polling_cycle
    
    # This just ensures early returns also have kalshi keys
    # By providing None for redis, it uses an in-memory lock skip mechanism, or fails to acquire lock, 
    # but let's just inspect the empty run_polling_cycle
    res = await run_polling_cycle(None)
    assert "kalshi_markets_polled" in res
    assert "kalshi_quotes_inserted" in res
    assert "kalshi_errors" in res
    assert "kalshi_skipped_no_alignment" in res
    assert "kalshi_skipped_no_market_id" in res
