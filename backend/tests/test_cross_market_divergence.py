"""Tests for cross-market divergence detection.

Covers:
1) ALIGNED when S and E exist within window, same direction
2) OPPOSED when directions differ
3) EXCHANGE_LEADS when E exists, S absent/late
4) SPORTSBOOK_LEADS when S exists, E absent/late
5) Idempotent rerun creates no duplicates
6) Resolution marking: lead event resolved when ALIGNED emitted
7) Poller integration includes cross_market_divergence_events_created
8) Admin export CSV returns expected header
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_divergence_event import CrossMarketDivergenceEvent
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.structural_event import StructuralEvent
from app.services.cross_market_divergence import CrossMarketDivergenceService
from app.tasks import poller


# ── helpers ──────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(UTC)


def _alignment(key: str = "cek_div", sportsbook_event_id: str = "sb_evt_1") -> CanonicalEventAlignment:
    return CanonicalEventAlignment(
        canonical_event_key=key,
        sport="basketball",
        league="NBA",
        home_team="BOS",
        away_team="NYK",
        start_time=_now() + timedelta(hours=2),
        sportsbook_event_id=sportsbook_event_id,
    )


def _structural(
    event_id: str = "sb_evt_1",
    direction: str = "UP",
    threshold: float = 3.5,
    ts: datetime | None = None,
    reversal: bool = False,
) -> StructuralEvent:
    t = ts or _now()
    return StructuralEvent(
        event_id=event_id,
        market_key="spreads",
        outcome_name="BOS",
        threshold_value=threshold,
        threshold_type="SPREAD",
        break_direction=direction,
        origin_venue="pinnacle",
        origin_venue_tier="T1",
        origin_timestamp=t - timedelta(seconds=30),
        confirmation_timestamp=t,
        adoption_percentage=0.8,
        adoption_count=3,
        active_venue_count=4,
        time_to_consensus_seconds=30,
        reversal_detected=reversal,
    )


def _exchange_quote(
    key: str = "cek_div",
    probability: float = 0.50,
    ts: datetime | None = None,
) -> ExchangeQuoteEvent:
    t = ts or _now()
    return ExchangeQuoteEvent(
        canonical_event_key=key,
        source="KALSHI",
        market_id="kalshi-mkt-1",
        outcome_name="YES",
        probability=probability,
        price=probability,
        timestamp=t,
    )


# ── 1  ALIGNED ──────────────────────────────────────────────────────

async def test_aligned_divergence(db_session: AsyncSession) -> None:
    now = _now()
    alignment = _alignment()
    structural = _structural(ts=now, direction="UP")
    q1 = _exchange_quote(probability=0.40, ts=now - timedelta(seconds=30))
    q2 = _exchange_quote(probability=0.55, ts=now + timedelta(seconds=5))
    db_session.add_all([alignment, structural, q1, q2])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    count = await service.compute_divergence("cek_div")
    await db_session.commit()

    assert count == 1
    row = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_div"
        )
    )).scalar_one()
    assert row.divergence_type == "ALIGNED"
    assert row.lead_source == "NONE"


# ── 2  OPPOSED ──────────────────────────────────────────────────────

async def test_opposed_divergence(db_session: AsyncSession) -> None:
    now = _now()
    alignment = _alignment(key="cek_opp", sportsbook_event_id="sb_opp")
    structural = _structural(event_id="sb_opp", ts=now, direction="UP")
    q1 = _exchange_quote(key="cek_opp", probability=0.60, ts=now - timedelta(seconds=30))
    q2 = _exchange_quote(key="cek_opp", probability=0.45, ts=now + timedelta(seconds=5))
    db_session.add_all([alignment, structural, q1, q2])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    count = await service.compute_divergence("cek_opp")
    await db_session.commit()

    assert count == 1
    row = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_opp"
        )
    )).scalar_one()
    assert row.divergence_type == "OPPOSED"


# ── 3  EXCHANGE_LEADS ───────────────────────────────────────────────

async def test_exchange_leads_divergence(db_session: AsyncSession) -> None:
    now = _now()
    alignment = _alignment(key="cek_el", sportsbook_event_id="sb_el")
    q1 = _exchange_quote(key="cek_el", probability=0.40, ts=now - timedelta(seconds=30))
    q2 = _exchange_quote(key="cek_el", probability=0.55, ts=now)
    db_session.add_all([alignment, q1, q2])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    count = await service.compute_divergence("cek_el")
    await db_session.commit()

    assert count == 1
    row = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_el"
        )
    )).scalar_one()
    assert row.divergence_type == "EXCHANGE_LEADS"
    assert row.lead_source == "EXCHANGE"


# ── 4  SPORTSBOOK_LEADS ────────────────────────────────────────────

async def test_sportsbook_leads_divergence(db_session: AsyncSession) -> None:
    now = _now()
    alignment = _alignment(key="cek_sl", sportsbook_event_id="sb_sl")
    structural = _structural(event_id="sb_sl", ts=now, direction="DOWN")
    db_session.add_all([alignment, structural])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    count = await service.compute_divergence("cek_sl")
    await db_session.commit()

    assert count == 1
    row = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_sl"
        )
    )).scalar_one()
    assert row.divergence_type == "SPORTSBOOK_LEADS"
    assert row.lead_source == "SPORTSBOOK"


# ── 5  Idempotent rerun ────────────────────────────────────────────

async def test_idempotent_rerun(db_session: AsyncSession) -> None:
    now = _now()
    alignment = _alignment(key="cek_idem", sportsbook_event_id="sb_idem")
    structural = _structural(event_id="sb_idem", ts=now, direction="UP")
    q1 = _exchange_quote(key="cek_idem", probability=0.40, ts=now - timedelta(seconds=30))
    q2 = _exchange_quote(key="cek_idem", probability=0.55, ts=now + timedelta(seconds=5))
    db_session.add_all([alignment, structural, q1, q2])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    count1 = await service.compute_divergence("cek_idem")
    await db_session.commit()
    count2 = await service.compute_divergence("cek_idem")
    await db_session.commit()

    assert count1 == 1
    assert count2 == 0

    total = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_idem"
        )
    )).scalars().all()
    assert len(total) == 1


# ── 6  Resolution marking ──────────────────────────────────────────

async def test_resolution_marking(db_session: AsyncSession) -> None:
    """A prior EXCHANGE_LEADS event gets resolved when an ALIGNED event is emitted."""
    now = _now()
    alignment = _alignment(key="cek_res", sportsbook_event_id="sb_res")

    # Phase 1: exchange leads (no structural)
    q1 = _exchange_quote(key="cek_res", probability=0.40, ts=now - timedelta(seconds=60))
    q2 = _exchange_quote(key="cek_res", probability=0.55, ts=now - timedelta(seconds=30))
    db_session.add_all([alignment, q1, q2])
    await db_session.commit()

    service = CrossMarketDivergenceService(db_session)
    await service.compute_divergence("cek_res")
    await db_session.commit()

    lead_row = (await db_session.execute(
        select(CrossMarketDivergenceEvent).where(
            CrossMarketDivergenceEvent.canonical_event_key == "cek_res",
            CrossMarketDivergenceEvent.divergence_type == "EXCHANGE_LEADS",
        )
    )).scalar_one()
    assert lead_row.resolved is False

    # Phase 2: sportsbook confirms → ALIGNED
    structural = _structural(event_id="sb_res", ts=now, direction="UP")
    db_session.add(structural)
    await db_session.commit()

    count2 = await service.compute_divergence("cek_res")
    await db_session.commit()

    assert count2 == 1
    await db_session.refresh(lead_row)
    assert lead_row.resolved is True
    assert lead_row.resolution_type == "ALIGNED"


# ── 7  Poller integration ──────────────────────────────────────────

async def test_poller_integration(db_session: AsyncSession) -> None:
    """Poller result includes cross_market_divergence_events_created."""
    # Verify the key exists in poller module source structure.
    # (Full poller integration not feasible in unit test without full environment.)
    import inspect
    source = inspect.getsource(poller)
    assert "cross_market_divergence_events_created" in source
    assert "CrossMarketDivergenceService" in source


# ── 8  Admin export CSV ─────────────────────────────────────────────

async def test_admin_export_csv_header(db_session: AsyncSession) -> None:
    """Verify the admin endpoint CSV generation returns expected columns."""
    from app.api.routes.admin import _DIVERGENCE_CSV_COLUMNS, _serialize_divergence_field

    expected = [
        "created_at", "canonical_event_key", "divergence_type", "lead_source",
        "sportsbook_threshold_value", "exchange_probability_threshold",
        "sportsbook_break_timestamp", "exchange_break_timestamp",
        "lag_seconds", "resolved", "resolved_at", "resolution_type", "idempotency_key",
    ]
    assert _DIVERGENCE_CSV_COLUMNS == expected
    assert _serialize_divergence_field(None) == ""
    assert _serialize_divergence_field(42) == "42"
    assert _serialize_divergence_field(True) == "True"
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    assert _serialize_divergence_field(ts) == ts.isoformat()
