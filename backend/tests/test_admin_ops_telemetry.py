from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle_kpi import CycleKpi
from app.models.signal import Signal
from app.models.user import User


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AdminOpsTelemetry123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _ensure_ops_tables(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: Signal.__table__.create(
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


def _build_signal(*, created_at: datetime, gate_mode: str | None, gate_pass: bool | None, bucket: str | None, skew: float | None) -> Signal:
    return Signal(
        event_id=f"evt-{uuid4().hex[:12]}",
        market="spreads",
        signal_type="MOVE",
        direction="UP",
        from_value=-3.5,
        to_value=-4.0,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=3,
        velocity_minutes=2.5,
        strength_score=72,
        created_at=created_at,
        metadata_json={"source": "test"},
        kalshi_gate_mode=gate_mode,
        kalshi_gate_pass=gate_pass,
        kalshi_skew_bucket=bucket,
        kalshi_liquidity_skew=skew,
        kalshi_gate_threshold=0.60,
    )


async def test_admin_ops_telemetry_includes_kalshi_shadow_windows(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_ops_tables(db_session)
    token = await _register(async_client, "admin-ops-telemetry@example.com")
    admin_user = (
        await db_session.execute(select(User).where(User.email == "admin-ops-telemetry@example.com"))
    ).scalar_one()
    admin_user.is_admin = True
    admin_user.tier = "pro"
    await db_session.commit()

    baseline_response = await async_client.get(
        "/api/v1/admin/ops/telemetry?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert baseline_response.status_code == 200, baseline_response.text
    baseline = baseline_response.json()["kalshi_shadow_skew"]

    now = datetime.now(UTC)
    db_session.add_all(
        [
            _build_signal(created_at=now - timedelta(hours=1), gate_mode="shadow", gate_pass=True, bucket="C", skew=0.67),
            _build_signal(created_at=now - timedelta(hours=2), gate_mode="shadow", gate_pass=False, bucket="A", skew=0.52),
            _build_signal(created_at=now - timedelta(hours=3), gate_mode="shadow", gate_pass=None, bucket=None, skew=None),
            _build_signal(created_at=now - timedelta(hours=4), gate_mode="enforce", gate_pass=True, bucket="D", skew=0.71),
            _build_signal(created_at=now - timedelta(days=2), gate_mode="shadow", gate_pass=True, bucket="D", skew=0.73),
            _build_signal(created_at=now - timedelta(days=8), gate_mode="shadow", gate_pass=False, bucket="B", skew=0.58),
            _build_signal(created_at=now - timedelta(days=1, minutes=5), gate_mode=None, gate_pass=None, bucket=None, skew=None),
        ]
    )
    db_session.add(
        CycleKpi(
            cycle_id=f"ops-telemetry-{uuid4().hex[:8]}",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=59),
            duration_ms=60_000,
            degraded=False,
            alerts_sent=2,
            alerts_failed=0,
            requests_used_delta=20,
            requests_remaining=900,
            requests_limit=1000,
            signals_created_total=2,
        )
    )
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/admin/ops/telemetry?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert "kalshi_shadow_skew" in payload
    shadow = payload["kalshi_shadow_skew"]
    assert shadow["mode"] in {"shadow", "enforce"}
    assert isinstance(shadow["threshold"], float)

    baseline_24h = baseline["last_24h"]
    baseline_7d = baseline["last_7d"]
    last_24h = shadow["last_24h"]
    assert last_24h["total_signals"] - baseline_24h["total_signals"] == 4
    assert last_24h["shadow_mode_signals"] - baseline_24h["shadow_mode_signals"] == 3
    assert last_24h["with_skew"] - baseline_24h["with_skew"] == 2
    assert last_24h["gate_pass_true"] - baseline_24h["gate_pass_true"] == 1
    assert last_24h["gate_pass_false"] - baseline_24h["gate_pass_false"] == 1
    assert last_24h["gate_pass_null"] - baseline_24h["gate_pass_null"] == 1
    pass_denominator_24h = last_24h["gate_pass_true"] + last_24h["gate_pass_false"]
    expected_pass_rate_24h = round((last_24h["gate_pass_true"] / pass_denominator_24h) * 100.0, 2)
    assert last_24h["pass_rate"] == expected_pass_rate_24h
    assert last_24h["buckets"]["A"] - baseline_24h["buckets"]["A"] == 1
    assert last_24h["buckets"]["B"] - baseline_24h["buckets"]["B"] == 0
    assert last_24h["buckets"]["C"] - baseline_24h["buckets"]["C"] == 1
    assert last_24h["buckets"]["D"] - baseline_24h["buckets"]["D"] == 0
    assert last_24h["buckets"]["NONE"] - baseline_24h["buckets"]["NONE"] == 1

    last_7d = shadow["last_7d"]
    assert last_7d["total_signals"] - baseline_7d["total_signals"] == 6
    assert last_7d["shadow_mode_signals"] - baseline_7d["shadow_mode_signals"] == 4
    assert last_7d["with_skew"] - baseline_7d["with_skew"] == 3
    assert last_7d["gate_pass_true"] - baseline_7d["gate_pass_true"] == 2
    assert last_7d["gate_pass_false"] - baseline_7d["gate_pass_false"] == 1
    assert last_7d["gate_pass_null"] - baseline_7d["gate_pass_null"] == 1
    pass_denominator_7d = last_7d["gate_pass_true"] + last_7d["gate_pass_false"]
    expected_pass_rate_7d = round((last_7d["gate_pass_true"] / pass_denominator_7d) * 100.0, 2)
    assert last_7d["pass_rate"] == expected_pass_rate_7d
    assert last_7d["buckets"]["A"] - baseline_7d["buckets"]["A"] == 1
    assert last_7d["buckets"]["B"] - baseline_7d["buckets"]["B"] == 0
    assert last_7d["buckets"]["C"] - baseline_7d["buckets"]["C"] == 1
    assert last_7d["buckets"]["D"] - baseline_7d["buckets"]["D"] == 1
    assert last_7d["buckets"]["NONE"] - baseline_7d["buckets"]["NONE"] == 1
