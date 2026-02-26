from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
from app.models.quote_move_event import QuoteMoveEvent
from app.models.structural_event import StructuralEvent
from app.models.structural_event_venue_participation import StructuralEventVenueParticipation
from app.services.structural_events import StructuralEventAnalysisService
from app.tasks import poller


def _quote_move(
    *,
    event_id: str,
    outcome_name: str,
    venue: str,
    venue_tier: str,
    old_line: float,
    new_line: float,
    timestamp: datetime,
) -> QuoteMoveEvent:
    return QuoteMoveEvent(
        event_id=event_id,
        market_key="spreads",
        outcome_name=outcome_name,
        venue=venue,
        venue_tier=venue_tier,
        old_line=old_line,
        new_line=new_line,
        delta=new_line - old_line,
        old_price=-110.0,
        new_price=-110.0,
        price_delta=0.0,
        timestamp=timestamp,
    )


def _snapshot(
    *,
    event_id: str,
    outcome_name: str,
    sportsbook_key: str,
    line: float,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=fetched_at + timedelta(hours=2),
        home_team="BOS",
        away_team="NYK",
        sportsbook_key=sportsbook_key,
        market="spreads",
        outcome_name=outcome_name,
        line=line,
        price=-110,
        fetched_at=fetched_at,
    )


async def _structural_rows(db_session: AsyncSession, event_id: str) -> list[StructuralEvent]:
    stmt = select(StructuralEvent).where(StructuralEvent.event_id == event_id).order_by(
        StructuralEvent.confirmation_timestamp.asc(),
        StructuralEvent.threshold_value.asc(),
    )
    return (await db_session.execute(stmt)).scalars().all()


async def test_single_non_t1_crossing_does_not_confirm(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_non_t1"
    db_session.add(
        _quote_move(
            event_id=event_id,
            outcome_name="BOS",
            venue="draftkings",
            venue_tier="T3",
            old_line=-3.0,
            new_line=-3.5,
            timestamp=now,
        )
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    detected = await service.detect_structural_events(event_id)
    assert detected == []
    assert await _structural_rows(db_session, event_id) == []


async def test_single_t1_crossing_confirms(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_t1_confirm"
    db_session.add(
        _quote_move(
            event_id=event_id,
            outcome_name="BOS",
            venue="pinnacle",
            venue_tier="T1",
            old_line=-3.0,
            new_line=-3.5,
            timestamp=now,
        )
    )
    db_session.add(_snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="pinnacle", line=-3.0, fetched_at=now))
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    detected = await service.detect_structural_events(event_id)
    assert len(detected) == 1
    row = detected[0]
    assert row.threshold_value == -3.5
    assert row.threshold_type == "HALF"
    assert row.break_direction == "DOWN"
    assert row.adoption_count == 1
    participation_rows = (
        await db_session.execute(
            select(StructuralEventVenueParticipation).where(
                StructuralEventVenueParticipation.structural_event_id == row.id
            )
        )
    ).scalars().all()
    assert len(participation_rows) == 1
    assert participation_rows[0].venue == "pinnacle"


async def test_multi_boundary_jump_creates_multiple_events(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_multi_boundary"
    db_session.add(
        _quote_move(
            event_id=event_id,
            outcome_name="BOS",
            venue="pinnacle",
            venue_tier="T1",
            old_line=-2.0,
            new_line=-3.5,
            timestamp=now,
        )
    )
    db_session.add(_snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="pinnacle", line=-2.0, fetched_at=now))
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    detected = await service.detect_structural_events(event_id)
    thresholds = {row.threshold_value for row in detected}
    assert len(detected) == 3
    assert thresholds == {-2.5, -3.0, -3.5}


async def test_origin_uses_earliest_timestamp(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_origin_earliest"
    first_ts = now
    second_ts = now + timedelta(minutes=1)
    db_session.add_all(
        [
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="draftkings",
                venue_tier="T3",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=first_ts,
            ),
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="fanduel",
                venue_tier="T3",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=second_ts,
            ),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="draftkings", line=-3.5, fetched_at=first_ts),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="fanduel", line=-3.5, fetched_at=second_ts),
        ]
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    await service.detect_structural_events(event_id)
    rows = await _structural_rows(db_session, event_id)
    assert len(rows) == 1
    assert rows[0].origin_venue == "draftkings"
    assert rows[0].origin_timestamp == first_ts
    assert rows[0].confirmation_timestamp == second_ts


async def test_idempotent_rerun_does_not_duplicate_events(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_idempotent"
    db_session.add(
        _quote_move(
            event_id=event_id,
            outcome_name="BOS",
            venue="pinnacle",
            venue_tier="T1",
            old_line=-3.0,
            new_line=-3.5,
            timestamp=now,
        )
    )
    db_session.add(_snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="pinnacle", line=-3.5, fetched_at=now))
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    first = await service.detect_structural_events(event_id)
    second = await service.detect_structural_events(event_id)
    assert len(first) == 1
    assert len(second) == 1
    rows = await _structural_rows(db_session, event_id)
    assert len(rows) == 1


async def test_participation_rows_not_duplicated_on_rerun(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_participation_dedupe"
    db_session.add_all(
        [
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="draftkings",
                venue_tier="T3",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=now,
            ),
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="fanduel",
                venue_tier="T3",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=now + timedelta(minutes=1),
            ),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="draftkings", line=-3.5, fetched_at=now),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="fanduel", line=-3.5, fetched_at=now),
        ]
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    await service.detect_structural_events(event_id)
    await service.detect_structural_events(event_id)

    event_row = (await db_session.execute(select(StructuralEvent).where(StructuralEvent.event_id == event_id))).scalars().one()
    participations = (
        await db_session.execute(
            select(StructuralEventVenueParticipation).where(
                StructuralEventVenueParticipation.structural_event_id == event_row.id
            )
        )
    ).scalars().all()
    assert len(participations) == 2


async def test_reversal_detection_requires_structural_confirmation(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_reversal"
    db_session.add_all(
        [
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="pinnacle",
                venue_tier="T1",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=now,
            ),
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="draftkings",
                venue_tier="T3",
                old_line=-4.0,
                new_line=-3.0,
                timestamp=now + timedelta(minutes=10),
            ),
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="fanduel",
                venue_tier="T3",
                old_line=-4.0,
                new_line=-3.0,
                timestamp=now + timedelta(minutes=11),
            ),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="pinnacle", line=-3.5, fetched_at=now),
        ]
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    await service.detect_structural_events(event_id)
    break_event = (
        await db_session.execute(
            select(StructuralEvent).where(
                StructuralEvent.event_id == event_id,
                StructuralEvent.break_direction == "DOWN",
                StructuralEvent.threshold_value == -3.5,
            )
        )
    ).scalars().one()
    assert break_event.reversal_detected is True
    assert break_event.reversal_timestamp == now + timedelta(minutes=11)
    assert break_event.break_hold_minutes == pytest.approx(11.0)


async def test_no_reversal_uses_last_observed_move_for_hold_minutes(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_no_reversal"
    db_session.add_all(
        [
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="pinnacle",
                venue_tier="T1",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=now,
            ),
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="draftkings",
                venue_tier="T3",
                old_line=-3.0,
                new_line=-4.0,
                timestamp=now + timedelta(minutes=20),
            ),
            _snapshot(event_id=event_id, outcome_name="BOS", sportsbook_key="pinnacle", line=-3.5, fetched_at=now),
        ]
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    await service.detect_structural_events(event_id)
    break_event = (
        await db_session.execute(
            select(StructuralEvent).where(
                StructuralEvent.event_id == event_id,
                StructuralEvent.break_direction == "DOWN",
                StructuralEvent.threshold_value == -3.5,
            )
        )
    ).scalars().one()
    assert break_event.reversal_detected is False
    assert break_event.break_hold_minutes == pytest.approx(20.0)


async def test_dispersion_none_when_insufficient_lines(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_struct_dispersion_none"
    db_session.add_all(
        [
            _quote_move(
                event_id=event_id,
                outcome_name="BOS",
                venue="pinnacle",
                venue_tier="T1",
                old_line=-3.0,
                new_line=-3.5,
                timestamp=now,
            ),
            _snapshot(
                event_id=event_id,
                outcome_name="BOS",
                sportsbook_key="pinnacle",
                line=-3.0,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                outcome_name="BOS",
                sportsbook_key="pinnacle",
                line=-3.5,
                fetched_at=now + timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    service = StructuralEventAnalysisService(db_session)
    await service.detect_structural_events(event_id)
    row = (await db_session.execute(select(StructuralEvent).where(StructuralEvent.event_id == event_id))).scalars().one()
    assert row.dispersion_pre is None
    assert row.dispersion_post is None


async def test_poller_integration_adds_structural_event_count(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    class _SessionCtx:
        def __init__(self, session: AsyncSession):
            self._session = session

        async def __aenter__(self) -> AsyncSession:
            return self._session

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    async def fake_ingest_odds_cycle(db, redis, eligible_event_ids=None):  # noqa: ANN001, ARG001
        return {
            "inserted": 1,
            "events_seen": 2,
            "events_processed": 2,
            "snapshots_inserted": 1,
            "event_ids": ["event_a", "event_b"],
            "event_ids_updated": ["event_a", "event_b"],
            "consensus_points_written": 0,
            "consensus_failed": False,
        }

    async def fake_detect_market_movements(db, redis, event_ids):  # noqa: ANN001, ARG001
        return []

    def fake_summarize_signals_by_type(signals):  # noqa: ANN001
        return {}

    async def fake_detect_propagation_events(db, event_ids):  # noqa: ANN001, ARG001
        return []

    async def fake_dispatch_alerts(db, signals, redis=None):  # noqa: ANN001, ARG001
        return {"sent": 0, "failed": 0}

    class FakeStructuralEventAnalysisService:
        def __init__(self, db: AsyncSession):  # noqa: ARG002
            pass

        async def detect_structural_events(self, game_id: str) -> list[object]:
            if game_id == "event_a":
                return [object(), object()]
            return [object()]

    monkeypatch.setattr(poller, "AsyncSessionLocal", lambda: _SessionCtx(db_session))
    monkeypatch.setattr(poller, "ingest_odds_cycle", fake_ingest_odds_cycle)
    monkeypatch.setattr(poller, "detect_market_movements", fake_detect_market_movements)
    monkeypatch.setattr(poller, "summarize_signals_by_type", fake_summarize_signals_by_type)
    monkeypatch.setattr(poller, "detect_propagation_events", fake_detect_propagation_events)
    monkeypatch.setattr(poller, "dispatch_discord_alerts_for_signals", fake_dispatch_alerts)
    monkeypatch.setattr(poller, "StructuralEventAnalysisService", FakeStructuralEventAnalysisService)

    result = await poller.run_polling_cycle(redis=None, close_capture_state=None)
    assert result["structural_events_created"] == 3
