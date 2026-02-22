from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.clv_record import ClvRecord
from app.models.cycle_kpi import CycleKpi
from app.models.signal import Signal


def _ops_headers(token: str | None = None) -> dict[str, str]:
    resolved = token if token is not None else get_settings().ops_internal_token
    return {"X-Stratum-Ops-Token": resolved}


def _signal(event_id: str, signal_type: str, market: str, outcome_name: str, created_at: datetime) -> Signal:
    return Signal(
        event_id=event_id,
        market=market,
        signal_type=signal_type,
        direction="UP",
        from_value=1.0,
        to_value=1.5,
        from_price=-110,
        to_price=-108,
        window_minutes=5,
        books_affected=3,
        velocity_minutes=2.0,
        strength_score=70,
        created_at=created_at,
        metadata_json={"outcome_name": outcome_name},
    )


async def test_operator_report_aggregates_with_internal_token(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await db_session.execute(delete(ClvRecord))
    await db_session.execute(delete(Signal))
    await db_session.execute(delete(CycleKpi))
    await db_session.commit()

    db_session.add_all(
        [
            CycleKpi(
                cycle_id="report_cycle_1",
                started_at=now - timedelta(hours=3),
                completed_at=now - timedelta(hours=3) + timedelta(seconds=1),
                duration_ms=1000,
                requests_used_delta=2,
                snapshots_inserted=100,
                consensus_points_written=10,
                signals_created_total=3,
                signals_created_by_type={"MOVE": 2, "DISLOCATION": 1},
                alerts_sent=5,
                alerts_failed=1,
                degraded=False,
            ),
            CycleKpi(
                cycle_id="report_cycle_2",
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2) + timedelta(seconds=2),
                duration_ms=2000,
                requests_used_delta=4,
                snapshots_inserted=200,
                consensus_points_written=20,
                signals_created_total=4,
                signals_created_by_type={"STEAM": 3, "DISLOCATION": 1},
                alerts_sent=4,
                alerts_failed=0,
                degraded=True,
            ),
            CycleKpi(
                cycle_id="report_cycle_3",
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1) + timedelta(seconds=3),
                duration_ms=3000,
                requests_used_delta=1,
                snapshots_inserted=50,
                consensus_points_written=5,
                signals_created_total=2,
                signals_created_by_type={"MOVE": 1, "STEAM": 1},
                alerts_sent=1,
                alerts_failed=2,
                degraded=False,
            ),
        ]
    )

    created = now - timedelta(hours=4)
    signals = [
        _signal("evt_report_1", "DISLOCATION", "spreads", "BOS", created),
        _signal("evt_report_2", "DISLOCATION", "totals", "Over", created),
        _signal("evt_report_3", "STEAM", "spreads", "BOS", created),
        _signal("evt_report_4", "MOVE", "h2h", "BOS", created),
        _signal("evt_report_5", "MOVE", "h2h", "BOS", created),
    ]
    db_session.add_all(signals)
    await db_session.flush()

    db_session.add_all(
        [
            ClvRecord(
                signal_id=signals[0].id,
                event_id=signals[0].event_id,
                signal_type=signals[0].signal_type,
                market=signals[0].market,
                outcome_name="BOS",
                entry_line=-3.5,
                entry_price=None,
                close_line=-3.0,
                close_price=None,
                clv_line=0.5,
                clv_prob=None,
                computed_at=now - timedelta(hours=2),
            ),
            ClvRecord(
                signal_id=signals[1].id,
                event_id=signals[1].event_id,
                signal_type=signals[1].signal_type,
                market=signals[1].market,
                outcome_name="Over",
                entry_line=226.0,
                entry_price=None,
                close_line=225.8,
                close_price=None,
                clv_line=-0.2,
                clv_prob=None,
                computed_at=now - timedelta(hours=2),
            ),
            ClvRecord(
                signal_id=signals[2].id,
                event_id=signals[2].event_id,
                signal_type=signals[2].signal_type,
                market=signals[2].market,
                outcome_name="BOS",
                entry_line=-4.2,
                entry_price=None,
                close_line=-4.1,
                close_price=None,
                clv_line=0.1,
                clv_prob=None,
                computed_at=now - timedelta(hours=1),
            ),
            ClvRecord(
                signal_id=signals[3].id,
                event_id=signals[3].event_id,
                signal_type=signals[3].signal_type,
                market=signals[3].market,
                outcome_name="BOS",
                entry_line=None,
                entry_price=120.0,
                close_line=None,
                close_price=110.0,
                clv_line=None,
                clv_prob=-0.03,
                computed_at=now - timedelta(hours=1),
            ),
            ClvRecord(
                signal_id=signals[4].id,
                event_id=signals[4].event_id,
                signal_type=signals[4].signal_type,
                market=signals[4].market,
                outcome_name="BOS",
                entry_line=None,
                entry_price=130.0,
                close_line=None,
                close_price=120.0,
                clv_line=None,
                clv_prob=0.02,
                computed_at=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/ops/report?days=7",
        headers=_ops_headers(),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["days"] == 7

    ops = payload["ops"]
    assert ops["total_cycles"] == 3
    assert abs(ops["avg_cycle_duration_ms"] - 2000.0) < 1e-9
    assert ops["degraded_cycles"] == 1
    assert ops["total_requests_used"] == 7
    assert ops["total_snapshots_inserted"] == 350
    assert ops["total_consensus_points_written"] == 35
    assert ops["total_signals_created"] == 9
    assert ops["signals_created_by_type"] == {"STEAM": 4, "MOVE": 3, "DISLOCATION": 2}

    reliability = payload["reliability"]
    assert reliability["alerts_sent"] == 10
    assert reliability["alerts_failed"] == 3
    assert abs(reliability["alert_failure_rate"] - (3 / 13)) < 1e-9

    by_signal = {row["signal_type"]: row for row in payload["performance"]["clv_by_signal_type"]}
    assert by_signal["DISLOCATION"]["count"] == 2
    assert abs(by_signal["DISLOCATION"]["pct_positive"] - 50.0) < 1e-9
    assert abs(by_signal["DISLOCATION"]["avg_clv_line"] - 0.15) < 1e-9
    assert by_signal["STEAM"]["count"] == 1
    assert abs(by_signal["STEAM"]["pct_positive"] - 100.0) < 1e-9
    assert by_signal["MOVE"]["count"] == 2
    assert abs(by_signal["MOVE"]["pct_positive"] - 50.0) < 1e-9
    assert abs(by_signal["MOVE"]["avg_clv_prob"] - (-0.005)) < 1e-9

    by_market = {row["market"]: row for row in payload["performance"]["clv_by_market"]}
    assert by_market["spreads"]["count"] == 2
    assert abs(by_market["spreads"]["pct_positive"] - 100.0) < 1e-9
    assert abs(by_market["spreads"]["avg_clv_line"] - 0.3) < 1e-9
    assert by_market["totals"]["count"] == 1
    assert abs(by_market["totals"]["pct_positive"] - 0.0) < 1e-9
    assert by_market["h2h"]["count"] == 2
    assert abs(by_market["h2h"]["pct_positive"] - 50.0) < 1e-9


async def test_operator_report_requires_internal_token(async_client: AsyncClient) -> None:
    missing = await async_client.get("/api/v1/ops/report?days=7")
    assert missing.status_code == 403

    wrong = await async_client.get(
        "/api/v1/ops/report?days=7",
        headers=_ops_headers("wrong-token"),
    )
    assert wrong.status_code == 403

    ok = await async_client.get(
        "/api/v1/ops/report?days=7",
        headers=_ops_headers(),
    )
    assert ok.status_code == 200
