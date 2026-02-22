from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle_kpi import CycleKpi
from app.models.ops_digest_sent import OpsDigestSent
from app.schemas.ops import OperatorReport
from app.services import ops_digest as ops_digest_service
from app.services.ops_digest import (
    build_ops_digest_embed,
    maybe_send_weekly_ops_digest,
    should_send_ops_digest,
)


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True


def test_should_send_ops_digest_window_logic() -> None:
    cfg = SimpleNamespace(
        ops_digest_weekday=1,
        ops_digest_hour_utc=13,
        ops_digest_minute_utc=0,
    )

    due_exact = datetime(2026, 2, 23, 13, 0, tzinfo=UTC)  # Monday
    assert should_send_ops_digest(due_exact, cfg) is True

    before_minute = datetime(2026, 2, 23, 12, 59, tzinfo=UTC)
    assert should_send_ops_digest(before_minute, cfg) is False

    later_same_hour = datetime(2026, 2, 23, 13, 27, tzinfo=UTC)
    assert should_send_ops_digest(later_same_hour, cfg) is True

    wrong_day = datetime(2026, 2, 24, 13, 0, tzinfo=UTC)  # Tuesday
    assert should_send_ops_digest(wrong_day, cfg) is False


async def test_ops_digest_webhook_not_configured_skips(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_enabled", True)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_webhook_url", "")
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_weekday", now.isoweekday())
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_hour_utc", now.hour)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_minute_utc", max(0, now.minute - 1))

    result = await maybe_send_weekly_ops_digest(db_session, redis=None, now_utc=now)
    assert result["sent"] is False
    assert result["reason"] == "webhook_not_configured"


async def test_ops_digest_dedupes_with_redis(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    redis = FakeRedis()
    sent_calls: list[dict] = []

    async def fake_send(_url: str, embed: dict) -> tuple[bool, int | None]:
        sent_calls.append(embed)
        return True, 204

    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_enabled", True)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_webhook_url", "https://discord.example/internal")
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_weekday", now.isoweekday())
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_hour_utc", now.hour)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_minute_utc", max(0, now.minute - 1))
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_lookback_days", 7)
    monkeypatch.setattr(ops_digest_service, "send_ops_digest", fake_send)

    db_session.add(
        CycleKpi(
            cycle_id="digest_cycle_redis",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(seconds=2),
            duration_ms=2000,
            requests_used_delta=2,
            snapshots_inserted=10,
            consensus_points_written=3,
            signals_created_total=2,
            signals_created_by_type={"MOVE": 2},
            alerts_sent=1,
            alerts_failed=0,
            degraded=False,
        )
    )
    await db_session.commit()

    first = await maybe_send_weekly_ops_digest(db_session, redis=redis, now_utc=now)
    second = await maybe_send_weekly_ops_digest(db_session, redis=redis, now_utc=now)

    assert first["sent"] is True
    assert second["sent"] is False
    assert second["reason"] == "already_sent"
    assert len(sent_calls) == 1


async def test_ops_digest_enabled_builds_payload_and_db_fallback_dedupe(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    captured_embeds: list[dict] = []

    async def fake_send(_url: str, embed: dict) -> tuple[bool, int | None]:
        captured_embeds.append(embed)
        return True, 204

    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_enabled", True)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_webhook_url", "https://discord.example/internal")
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_weekday", now.isoweekday())
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_hour_utc", now.hour)
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_minute_utc", max(0, now.minute - 1))
    monkeypatch.setattr(ops_digest_service.settings, "ops_digest_lookback_days", 7)
    monkeypatch.setattr(ops_digest_service, "send_ops_digest", fake_send)

    db_session.add(
        CycleKpi(
            cycle_id="digest_cycle_db",
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(seconds=5),
            duration_ms=5000,
            requests_used_delta=4,
            requests_remaining=350,
            snapshots_inserted=25,
            consensus_points_written=6,
            signals_created_total=4,
            signals_created_by_type={"DISLOCATION": 2, "STEAM": 2},
            alerts_sent=3,
            alerts_failed=1,
            degraded=True,
        )
    )
    await db_session.commit()

    result = await maybe_send_weekly_ops_digest(db_session, redis=None, now_utc=now)
    assert result["sent"] is True
    assert len(captured_embeds) == 1

    embed = captured_embeds[0]
    assert embed["title"] == "STRATUM OPS WEEKLY"
    field_names = [field["name"] for field in embed["fields"]]
    assert "Period" in field_names
    assert "Ops" in field_names
    assert "API" in field_names
    assert "Throughput" in field_names
    assert "Signals (Top 5)" in field_names
    assert "Alerts" in field_names
    assert "Performance (Top 3 by avg CLV)" in field_names
    assert embed["footer"]["text"] == "Internal — X-Stratum-Ops-Token protected"

    sent_rows = (await db_session.execute(select(OpsDigestSent))).scalars().all()
    assert len(sent_rows) == 1


def test_build_ops_digest_embed_required_fields() -> None:
    report = OperatorReport(
        days=7,
        period_start=datetime(2026, 2, 16, 13, 0, tzinfo=UTC),
        period_end=datetime(2026, 2, 23, 13, 0, tzinfo=UTC),
        ops={
            "total_cycles": 10,
            "avg_cycle_duration_ms": 2200.0,
            "degraded_cycles": 2,
            "total_requests_used": 50,
            "avg_requests_remaining": 400.0,
            "total_snapshots_inserted": 1000,
            "total_consensus_points_written": 250,
            "total_signals_created": 40,
            "signals_created_by_type": {"MOVE": 10, "DISLOCATION": 8, "STEAM": 6},
        },
        performance={
            "clv_by_signal_type": [
                {
                    "signal_type": "DISLOCATION",
                    "count": 8,
                    "pct_positive": 62.5,
                    "avg_clv_line": 0.25,
                    "avg_clv_prob": 0.01,
                }
            ],
            "clv_by_market": [],
        },
        reliability={
            "alerts_sent": 20,
            "alerts_failed": 2,
            "alert_failure_rate": 2 / 22,
        },
    )

    embed = build_ops_digest_embed(report)
    assert embed["title"] == "STRATUM OPS WEEKLY"
    assert embed["footer"]["text"] == "Internal — X-Stratum-Ops-Token protected"
