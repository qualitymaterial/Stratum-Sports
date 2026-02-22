from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.cycle_kpi import CycleKpi
from app.services.kpis import build_cycle_kpi, cleanup_old_cycle_kpis, persist_cycle_kpi


def _ops_headers(token: str | None = None) -> dict[str, str]:
    resolved = token if token is not None else get_settings().ops_internal_token
    return {"X-Stratum-Ops-Token": resolved}


async def test_persist_cycle_kpi_upsert_by_cycle_id(db_session: AsyncSession) -> None:
    started_at = datetime.now(UTC) - timedelta(minutes=2)
    completed_at = started_at + timedelta(seconds=4)
    cycle_id = "cycle_upsert_001"

    first = build_cycle_kpi(
        {
            "cycle_id": cycle_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": 4000,
            "requests_used_delta": 3,
            "events_processed": 5,
            "snapshots_inserted": 120,
            "signals_created_total": 4,
            "signals_created_by_type": {"MOVE": 2, "DISLOCATION": 2},
            "alerts_sent": 1,
            "alerts_failed": 0,
            "degraded": False,
            "notes": {"phase": "initial"},
        }
    )
    await persist_cycle_kpi(db_session, first)

    second = build_cycle_kpi(
        {
            "cycle_id": cycle_id,
            "started_at": started_at,
            "completed_at": completed_at + timedelta(seconds=1),
            "duration_ms": 5000,
            "requests_used_delta": 4,
            "events_processed": 6,
            "snapshots_inserted": 140,
            "signals_created_total": 5,
            "signals_created_by_type": {"MOVE": 3, "STEAM": 2},
            "alerts_sent": 2,
            "alerts_failed": 1,
            "degraded": True,
            "notes": {"phase": "updated"},
        }
    )
    await persist_cycle_kpi(db_session, second)

    rows = (await db_session.execute(select(CycleKpi).where(CycleKpi.cycle_id == cycle_id))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.duration_ms == 5000
    assert row.requests_used_delta == 4
    assert row.signals_created_total == 5
    assert row.signals_created_by_type == {"MOVE": 3, "STEAM": 2}
    assert row.alerts_failed == 1
    assert row.degraded is True


async def test_cleanup_old_cycle_kpis_deletes_expired(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    old_time = now - timedelta(days=40)
    new_time = now - timedelta(days=2)

    db_session.add_all(
        [
            CycleKpi(
                cycle_id="cycle_cleanup_old",
                started_at=old_time,
                completed_at=old_time + timedelta(seconds=2),
                duration_ms=2000,
                created_at=old_time,
            ),
            CycleKpi(
                cycle_id="cycle_cleanup_new",
                started_at=new_time,
                completed_at=new_time + timedelta(seconds=1),
                duration_ms=1000,
                created_at=new_time,
            ),
        ]
    )
    await db_session.commit()

    deleted = await cleanup_old_cycle_kpis(db_session, retention_days=30)
    assert deleted == 1

    remaining = (
        await db_session.execute(
            select(CycleKpi).where(
                CycleKpi.cycle_id.in_(["cycle_cleanup_old", "cycle_cleanup_new"])
            )
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].cycle_id == "cycle_cleanup_new"


async def test_ops_cycles_summary_aggregates_with_internal_token(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            CycleKpi(
                cycle_id="cycle_ops_1",
                started_at=now - timedelta(hours=3),
                completed_at=now - timedelta(hours=3) + timedelta(seconds=3),
                duration_ms=3000,
                requests_used_delta=2,
                snapshots_inserted=100,
                signals_created_total=3,
                signals_created_by_type={"MOVE": 2, "DISLOCATION": 1},
                alerts_sent=1,
                alerts_failed=0,
            ),
            CycleKpi(
                cycle_id="cycle_ops_2",
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2) + timedelta(seconds=4),
                duration_ms=4000,
                requests_used_delta=3,
                snapshots_inserted=120,
                signals_created_total=4,
                signals_created_by_type={"MOVE": 1, "STEAM": 3},
                alerts_sent=2,
                alerts_failed=1,
            ),
            CycleKpi(
                cycle_id="cycle_ops_3",
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1) + timedelta(seconds=5),
                duration_ms=5000,
                requests_used_delta=4,
                snapshots_inserted=140,
                signals_created_total=5,
                signals_created_by_type={"DISLOCATION": 2, "STEAM": 3},
                alerts_sent=1,
                alerts_failed=1,
            ),
        ]
    )
    await db_session.commit()

    headers = _ops_headers()

    list_resp = await async_client.get("/api/v1/ops/cycles?days=7&limit=200", headers=headers)
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert len(list_payload) >= 3

    summary_resp = await async_client.get("/api/v1/ops/cycles/summary?days=7", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_cycles"] >= 3
    assert summary["total_snapshots_inserted"] >= 360
    assert summary["total_signals_created"] >= 12
    assert summary["alerts_sent"] >= 4
    assert summary["alerts_failed"] >= 2
    assert summary["requests_used_delta"] >= 9
    top_signal_types = {row["signal_type"]: row["count"] for row in summary["top_signal_types"]}
    assert top_signal_types.get("STEAM", 0) >= 6


async def test_ops_cycles_endpoints_require_internal_token(async_client: AsyncClient) -> None:
    no_header_list = await async_client.get("/api/v1/ops/cycles?days=7&limit=20")
    assert no_header_list.status_code == 403

    wrong_header_list = await async_client.get(
        "/api/v1/ops/cycles?days=7&limit=20",
        headers=_ops_headers("wrong-token"),
    )
    assert wrong_header_list.status_code == 403

    ok_header_list = await async_client.get(
        "/api/v1/ops/cycles?days=7&limit=20",
        headers=_ops_headers(),
    )
    assert ok_header_list.status_code == 200

    no_header_summary = await async_client.get("/api/v1/ops/cycles/summary?days=7")
    assert no_header_summary.status_code == 403

    wrong_header_summary = await async_client.get(
        "/api/v1/ops/cycles/summary?days=7",
        headers=_ops_headers("wrong-token"),
    )
    assert wrong_header_summary.status_code == 403

    ok_header_summary = await async_client.get(
        "/api/v1/ops/cycles/summary?days=7",
        headers=_ops_headers(),
    )
    assert ok_header_summary.status_code == 200
