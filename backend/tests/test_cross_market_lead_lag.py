"""Tests for Phase 2 cross-market lead-lag foundation.

Covers:
- Probability threshold detection (Decimal-safe)
- Sportsbook leads exchange
- Exchange leads sportsbook
- Idempotent rerun
- Unique constraint enforcement (no duplicate lead-lag rows)
- Poller integration
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_lead_lag_event import CrossMarketLeadLagEvent
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.structural_event import StructuralEvent
from app.services.cross_market_lead_lag import (
    CrossMarketLeadLagService,
    detect_probability_crossings,
)
from app.tasks import poller


# ── helpers ─────────────────────────────────────────────────────────


def _alignment(
    *,
    canonical_event_key: str,
    sportsbook_event_id: str,
    sport: str = "basketball",
    league: str = "NBA",
) -> CanonicalEventAlignment:
    return CanonicalEventAlignment(
        canonical_event_key=canonical_event_key,
        sport=sport,
        league=league,
        home_team="BOS",
        away_team="NYK",
        start_time=datetime.now(UTC) + timedelta(hours=2),
        sportsbook_event_id=sportsbook_event_id,
    )


def _exchange_quote(
    *,
    canonical_event_key: str,
    source: str = "KALSHI",
    market_id: str = "kalshi-mkt-1",
    outcome_name: str = "YES",
    probability: float,
    timestamp: datetime,
    price: float | None = None,
) -> ExchangeQuoteEvent:
    return ExchangeQuoteEvent(
        canonical_event_key=canonical_event_key,
        source=source,
        market_id=market_id,
        outcome_name=outcome_name,
        probability=probability,
        price=price,
        timestamp=timestamp,
    )


def _structural_event(
    *,
    event_id: str,
    threshold_value: float,
    break_direction: str = "DOWN",
    confirmation_timestamp: datetime,
) -> StructuralEvent:
    """Minimal StructuralEvent for lead-lag tests."""
    return StructuralEvent(
        event_id=event_id,
        market_key="spreads",
        outcome_name="BOS",
        threshold_value=threshold_value,
        threshold_type="HALF",
        break_direction=break_direction,
        origin_venue="pinnacle",
        origin_venue_tier="T1",
        origin_timestamp=confirmation_timestamp - timedelta(seconds=30),
        confirmation_timestamp=confirmation_timestamp,
        adoption_percentage=1.0,
        adoption_count=1,
        active_venue_count=1,
        time_to_consensus_seconds=30,
        reversal_detected=False,
    )


async def _lead_lag_rows(db: AsyncSession, cek: str) -> list[CrossMarketLeadLagEvent]:
    stmt = (
        select(CrossMarketLeadLagEvent)
        .where(CrossMarketLeadLagEvent.canonical_event_key == cek)
        .order_by(CrossMarketLeadLagEvent.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── 1  probability threshold detection ──────────────────────────────


async def test_probability_threshold_single_step_up(db_session: AsyncSession) -> None:
    """0.50 → 0.53 crosses the 0.525 boundary only."""
    now = datetime.now(UTC)
    quotes = [
        _exchange_quote(
            canonical_event_key="evt1", probability=0.50, timestamp=now,
        ),
        _exchange_quote(
            canonical_event_key="evt1", probability=0.53,
            timestamp=now + timedelta(seconds=30),
        ),
    ]
    crossings = detect_probability_crossings(quotes)
    assert len(crossings) == 1
    assert crossings[0].threshold == Decimal("0.525")


async def test_probability_threshold_multi_step_up(db_session: AsyncSession) -> None:
    """0.50 → 0.60 crosses 0.525, 0.550, 0.575, 0.600."""
    now = datetime.now(UTC)
    quotes = [
        _exchange_quote(
            canonical_event_key="evt2", probability=0.50, timestamp=now,
        ),
        _exchange_quote(
            canonical_event_key="evt2", probability=0.60,
            timestamp=now + timedelta(seconds=60),
        ),
    ]
    crossings = detect_probability_crossings(quotes)
    thresholds = [c.threshold for c in crossings]
    assert thresholds == [
        Decimal("0.525"),
        Decimal("0.550"),
        Decimal("0.575"),
        Decimal("0.600"),
    ]


async def test_probability_threshold_downward(db_session: AsyncSession) -> None:
    """0.60 → 0.50 crosses 0.575, 0.550, 0.525, 0.500."""
    now = datetime.now(UTC)
    quotes = [
        _exchange_quote(
            canonical_event_key="evt3", probability=0.60, timestamp=now,
        ),
        _exchange_quote(
            canonical_event_key="evt3", probability=0.50,
            timestamp=now + timedelta(seconds=60),
        ),
    ]
    crossings = detect_probability_crossings(quotes)
    thresholds = [c.threshold for c in crossings]
    assert thresholds == [
        Decimal("0.500"),
        Decimal("0.525"),
        Decimal("0.550"),
        Decimal("0.575"),
    ]


async def test_probability_threshold_no_crossing(db_session: AsyncSession) -> None:
    """0.51 → 0.52 stays within the same 0.025 band."""
    now = datetime.now(UTC)
    quotes = [
        _exchange_quote(
            canonical_event_key="evt4", probability=0.51, timestamp=now,
        ),
        _exchange_quote(
            canonical_event_key="evt4", probability=0.52,
            timestamp=now + timedelta(seconds=30),
        ),
    ]
    crossings = detect_probability_crossings(quotes)
    assert crossings == []


async def test_probability_threshold_decimal_safe(db_session: AsyncSession) -> None:
    """Verify Decimal arithmetic avoids float drift (0.1+0.2 ≠ 0.3)."""
    now = datetime.now(UTC)
    # 0.075 → 0.125 should cross exactly 0.100
    quotes = [
        _exchange_quote(
            canonical_event_key="evt5", probability=0.075, timestamp=now,
        ),
        _exchange_quote(
            canonical_event_key="evt5", probability=0.125,
            timestamp=now + timedelta(seconds=30),
        ),
    ]
    crossings = detect_probability_crossings(quotes)
    # 0.075 -> 0.125 crosses 0.100 and lands exactly on 0.125
    assert len(crossings) == 2
    assert crossings[0].threshold == Decimal("0.100")
    assert crossings[1].threshold == Decimal("0.125")
    # Verify they are exact Decimals, not rounded floats
    assert isinstance(crossings[0].threshold, Decimal)
    assert isinstance(crossings[1].threshold, Decimal)


# ── 2  sportsbook leads exchange ────────────────────────────────────


async def test_sportsbook_leads_exchange(db_session: AsyncSession) -> None:
    """Sportsbook break occurs before exchange break → lead_source = SPORTSBOOK."""
    cek = "cek_sb_leads"
    sb_event_id = "sb_event_leads"
    now = datetime.now(UTC)

    # Sportsbook breaks at t=0
    sportsbook_ts = now
    # Exchange crosses threshold at t=+3min
    exchange_ts = now + timedelta(minutes=3)

    db_session.add(_alignment(
        canonical_event_key=cek, sportsbook_event_id=sb_event_id,
    ))
    db_session.add(_structural_event(
        event_id=sb_event_id,
        threshold_value=-3.5,
        confirmation_timestamp=sportsbook_ts,
    ))
    db_session.add_all([
        _exchange_quote(
            canonical_event_key=cek, probability=0.50,
            timestamp=exchange_ts - timedelta(seconds=30),
        ),
        _exchange_quote(
            canonical_event_key=cek, probability=0.53,
            timestamp=exchange_ts,
        ),
    ])
    await db_session.commit()

    service = CrossMarketLeadLagService(db_session)
    inserted = await service.compute_lead_lag(cek)
    await db_session.commit()

    assert inserted == 1
    rows = await _lead_lag_rows(db_session, cek)
    assert len(rows) == 1
    row = rows[0]
    assert row.lead_source == "SPORTSBOOK"
    assert row.sportsbook_break_timestamp == sportsbook_ts
    assert row.exchange_break_timestamp == exchange_ts
    assert row.lag_seconds == 180  # 3 minutes


# ── 3  exchange leads sportsbook ────────────────────────────────────


async def test_exchange_leads_sportsbook(db_session: AsyncSession) -> None:
    """Exchange break occurs before sportsbook break → lead_source = EXCHANGE."""
    cek = "cek_ex_leads"
    sb_event_id = "sb_event_ex_leads"
    now = datetime.now(UTC)

    # Exchange crosses threshold at t=0
    exchange_ts = now
    # Sportsbook breaks at t=+5min
    sportsbook_ts = now + timedelta(minutes=5)

    db_session.add(_alignment(
        canonical_event_key=cek, sportsbook_event_id=sb_event_id,
    ))
    db_session.add(_structural_event(
        event_id=sb_event_id,
        threshold_value=-3.5,
        confirmation_timestamp=sportsbook_ts,
    ))
    db_session.add_all([
        _exchange_quote(
            canonical_event_key=cek, probability=0.50,
            timestamp=exchange_ts - timedelta(seconds=30),
        ),
        _exchange_quote(
            canonical_event_key=cek, probability=0.53,
            timestamp=exchange_ts,
        ),
    ])
    await db_session.commit()

    service = CrossMarketLeadLagService(db_session)
    inserted = await service.compute_lead_lag(cek)
    await db_session.commit()

    assert inserted == 1
    rows = await _lead_lag_rows(db_session, cek)
    assert len(rows) == 1
    row = rows[0]
    assert row.lead_source == "EXCHANGE"
    assert row.lag_seconds == 300  # 5 minutes


# ── 4  idempotent rerun ─────────────────────────────────────────────


async def test_idempotent_rerun(db_session: AsyncSession) -> None:
    """Running compute_lead_lag twice produces no duplicate rows."""
    cek = "cek_idempotent"
    sb_event_id = "sb_event_idempotent"
    now = datetime.now(UTC)

    db_session.add(_alignment(
        canonical_event_key=cek, sportsbook_event_id=sb_event_id,
    ))
    db_session.add(_structural_event(
        event_id=sb_event_id,
        threshold_value=-3.5,
        confirmation_timestamp=now,
    ))
    db_session.add_all([
        _exchange_quote(
            canonical_event_key=cek, probability=0.50,
            timestamp=now - timedelta(seconds=30),
        ),
        _exchange_quote(
            canonical_event_key=cek, probability=0.53,
            timestamp=now + timedelta(minutes=2),
        ),
    ])
    await db_session.commit()

    service = CrossMarketLeadLagService(db_session)
    first = await service.compute_lead_lag(cek)
    await db_session.commit()
    second = await service.compute_lead_lag(cek)
    await db_session.commit()

    assert first == 1
    assert second == 0  # no new rows on rerun
    rows = await _lead_lag_rows(db_session, cek)
    assert len(rows) == 1


# ── 5  unique constraint prevents duplicates ────────────────────────


async def test_no_duplicate_lead_lag_rows(db_session: AsyncSession) -> None:
    """Direct insert test: same unique key → only 1 row."""
    cek = "cek_dup_test"
    sb_event_id = "sb_event_dup"
    now = datetime.now(UTC)

    db_session.add(_alignment(
        canonical_event_key=cek, sportsbook_event_id=sb_event_id,
    ))
    db_session.add(_structural_event(
        event_id=sb_event_id,
        threshold_value=-3.5,
        confirmation_timestamp=now,
    ))
    db_session.add_all([
        _exchange_quote(
            canonical_event_key=cek, probability=0.50,
            timestamp=now - timedelta(minutes=1),
        ),
        _exchange_quote(
            canonical_event_key=cek, probability=0.53,
            timestamp=now + timedelta(minutes=1),
        ),
    ])
    await db_session.commit()

    service = CrossMarketLeadLagService(db_session)
    await service.compute_lead_lag(cek)
    await db_session.commit()
    # Second run with same data
    await service.compute_lead_lag(cek)
    await db_session.commit()
    # Third run for good measure
    await service.compute_lead_lag(cek)
    await db_session.commit()

    rows = await _lead_lag_rows(db_session, cek)
    assert len(rows) == 1


# ── 6  no alignment row → 0 results ────────────────────────────────


async def test_no_alignment_returns_zero(db_session: AsyncSession) -> None:
    """compute_lead_lag returns 0 when no CanonicalEventAlignment exists."""
    service = CrossMarketLeadLagService(db_session)
    result = await service.compute_lead_lag("nonexistent_key")
    assert result == 0


# ── 7  outside alignment window → skipped ───────────────────────────


async def test_outside_alignment_window_skipped(db_session: AsyncSession) -> None:
    """Exchange crossings outside ±10 min of sportsbook break are not aligned."""
    cek = "cek_outside_window"
    sb_event_id = "sb_event_outside"
    now = datetime.now(UTC)

    db_session.add(_alignment(
        canonical_event_key=cek, sportsbook_event_id=sb_event_id,
    ))
    db_session.add(_structural_event(
        event_id=sb_event_id,
        threshold_value=-3.5,
        confirmation_timestamp=now,
    ))
    # Exchange crossing is 15 minutes away — outside the 10-min window
    db_session.add_all([
        _exchange_quote(
            canonical_event_key=cek, probability=0.50,
            timestamp=now + timedelta(minutes=14),
        ),
        _exchange_quote(
            canonical_event_key=cek, probability=0.53,
            timestamp=now + timedelta(minutes=15),
        ),
    ])
    await db_session.commit()

    service = CrossMarketLeadLagService(db_session)
    inserted = await service.compute_lead_lag(cek)
    assert inserted == 0


# ── 8  poller integration ───────────────────────────────────────────


async def test_poller_integration_adds_cross_market_count(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """Verify poller result includes cross_market_events_created."""

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
            return [object()]

    class FakeCrossMarketLeadLagService:
        def __init__(self, db: AsyncSession):  # noqa: ARG002
            pass

        async def compute_lead_lag(self, canonical_event_key: str) -> int:  # noqa: ARG002
            return 2

    monkeypatch.setattr(poller, "AsyncSessionLocal", lambda: _SessionCtx(db_session))
    monkeypatch.setattr(poller, "ingest_odds_cycle", fake_ingest_odds_cycle)
    monkeypatch.setattr(poller, "detect_market_movements", fake_detect_market_movements)
    monkeypatch.setattr(poller, "summarize_signals_by_type", fake_summarize_signals_by_type)
    monkeypatch.setattr(poller, "detect_propagation_events", fake_detect_propagation_events)
    monkeypatch.setattr(poller, "dispatch_discord_alerts_for_signals", fake_dispatch_alerts)
    monkeypatch.setattr(poller, "StructuralEventAnalysisService", FakeStructuralEventAnalysisService)
    monkeypatch.setattr(poller, "CrossMarketLeadLagService", FakeCrossMarketLeadLagService)

    # Seed an alignment row so the poller finds it
    db_session.add(_alignment(
        canonical_event_key="cek_poller", sportsbook_event_id="event_a",
    ))
    await db_session.commit()

    result = await poller.run_polling_cycle(redis=None, close_capture_state=None)
    assert "cross_market_events_created" in result
    assert result["cross_market_events_created"] >= 0
    assert result["structural_events_created"] == 2  # 1 per event_id
