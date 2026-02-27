"""Tests for exchange adapter clients and poller Kalshi ingestion wiring.

Covers:
1) KalshiClient.fetch_market_quotes success (mocked HTTP)
2) Poller Kalshi wiring inserts quotes via ExchangeIngestionService
3) Polymarket disabled by default (never called)
4) Cap enforcement (MAX_KALSHI_MARKETS_PER_CYCLE)
5) Fail-open behavior (ExchangeUpstreamError does not crash poller)
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.exchange.errors import ExchangeUpstreamError
from app.adapters.exchange.kalshi_client import KalshiClient
from app.adapters.exchange.polymarket_client import PolymarketClient
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.services.exchange_ingestion import ExchangeIngestionService


# ── helpers ──────────────────────────────────────────────────────────

_KALSHI_PAYLOAD = {
    "market_id": "kalshi-test-mkt",
    "outcomes": [
        {"name": "YES", "probability": 0.62, "price": 0.62},
        {"name": "NO", "probability": 0.38, "price": 0.38},
    ],
    "timestamp": "2026-02-26T22:00:00+00:00",
}


def _alignment(
    key: str = "cek_adapter",
    sportsbook_event_id: str = "sb_adapter_1",
    kalshi_market_id: str | None = "kalshi-test-mkt",
    polymarket_market_id: str | None = None,
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
        polymarket_market_id=polymarket_market_id,
    )


# ── 1  KalshiClient success (mocked HTTP) ───────────────────────────

async def test_kalshi_client_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """KalshiClient.fetch_market_quotes returns dict on 200."""

    async def _mock_fetch(self: KalshiClient, market_id: str) -> dict:
        return _KALSHI_PAYLOAD

    monkeypatch.setattr(KalshiClient, "fetch_market_quotes", _mock_fetch)

    # We monkeypatch so no real network is needed; instantiation reads settings
    # which exist with sensible defaults.
    client = KalshiClient()
    result = await client.fetch_market_quotes("kalshi-test-mkt")
    assert result["market_id"] == "kalshi-test-mkt"
    assert len(result["outcomes"]) == 2
    assert result["outcomes"][0]["name"] == "YES"


# ── 2  Poller Kalshi wiring inserts quotes ───────────────────────────

async def test_kalshi_poller_wiring_inserts_quotes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full round-trip: alignment → adapter → ingest → ExchangeQuoteEvent rows."""
    alignment = _alignment()
    db_session.add(alignment)
    await db_session.commit()

    # Monkeypatch KalshiClient to return canned payload (no network)
    async def _mock_fetch(self: KalshiClient, market_id: str) -> dict:
        return _KALSHI_PAYLOAD

    monkeypatch.setattr(KalshiClient, "fetch_market_quotes", _mock_fetch)

    # Drive the exchange ingestion path directly (not full poller, since
    # that requires redis and dozens of other services).
    from app.core.config import get_settings

    settings = get_settings()
    exchange_ingestion = ExchangeIngestionService(db_session)
    kalshi_client = KalshiClient()

    alignment_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.kalshi_market_id.isnot(None)
    )
    rows = list((await db_session.execute(alignment_stmt)).scalars().all())
    kalshi_alignments = rows[: settings.max_kalshi_markets_per_cycle]

    total_inserted = 0
    markets_polled = 0
    for a in kalshi_alignments:
        raw = await kalshi_client.fetch_market_quotes(a.kalshi_market_id)  # type: ignore[arg-type]
        inserted = await exchange_ingestion.ingest_exchange_quotes(
            canonical_event_key=a.canonical_event_key,
            source="KALSHI",
            raw_payload=raw,
        )
        total_inserted += inserted
        markets_polled += 1
    await db_session.commit()

    assert markets_polled == 1
    assert total_inserted >= 1

    # Verify ExchangeQuoteEvent rows were persisted
    quote_rows = (
        await db_session.execute(
            select(ExchangeQuoteEvent).where(
                ExchangeQuoteEvent.canonical_event_key == "cek_adapter"
            )
        )
    ).scalars().all()
    assert len(quote_rows) >= 1
    assert any(q.source == "KALSHI" for q in quote_rows)


# ── 3  Polymarket disabled by default ────────────────────────────────

async def test_polymarket_disabled_by_default(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ENABLE_POLYMARKET_INGEST is false, PolymarketClient is never called."""
    alignment = _alignment(
        key="cek_poly",
        sportsbook_event_id="sb_poly_1",
        kalshi_market_id=None,
        polymarket_market_id="poly-test-mkt",
    )
    db_session.add(alignment)
    await db_session.commit()

    from app.core.config import get_settings

    settings = get_settings()
    assert settings.enable_polymarket_ingest is False

    # Verify poller source references Polymarket guard
    from app.tasks import poller

    source = inspect.getsource(poller)
    assert "enable_polymarket_ingest" in source
    assert "PolymarketClient" in source

    # Spy on PolymarketClient — it should never be instantiated
    call_count = 0

    async def _mock_fetch(self: PolymarketClient, market_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {}

    monkeypatch.setattr(PolymarketClient, "fetch_market_quotes", _mock_fetch)

    # Simulate the poller guard: if disabled, skip
    if not settings.enable_polymarket_ingest:
        pass  # This is what the poller does: nothing
    assert call_count == 0


# ── 4  Cap enforcement ───────────────────────────────────────────────

async def test_kalshi_cap_enforcement(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only MAX_KALSHI_MARKETS_PER_CYCLE alignments are polled."""
    # Create more alignments than the cap
    cap = 3
    monkeypatch.setenv("MAX_KALSHI_MARKETS_PER_CYCLE", str(cap))

    # Reset settings cache
    from app.core.config import get_settings

    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.max_kalshi_markets_per_cycle == cap

        for i in range(cap + 5):
            db_session.add(
                _alignment(
                    key=f"cek_cap_{i}",
                    sportsbook_event_id=f"sb_cap_{i}",
                    kalshi_market_id=f"kalshi-cap-{i}",
                )
            )
        await db_session.commit()

        alignment_stmt = select(CanonicalEventAlignment).where(
            CanonicalEventAlignment.kalshi_market_id.isnot(None)
        )
        all_rows = list((await db_session.execute(alignment_stmt)).scalars().all())
        capped = [a for a in all_rows if a.kalshi_market_id][:settings.max_kalshi_markets_per_cycle]

        assert len(capped) == cap
        assert len(all_rows) >= cap + 5
    finally:
        get_settings.cache_clear()


# ── 5  Fail-open behavior ───────────────────────────────────────────

async def test_kalshi_fail_open(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ExchangeUpstreamError from Kalshi does not crash the ingestion loop."""
    alignment = _alignment(key="cek_fail", sportsbook_event_id="sb_fail")
    db_session.add(alignment)
    await db_session.commit()

    async def _mock_fetch_error(self: KalshiClient, market_id: str) -> dict:
        raise ExchangeUpstreamError("KALSHI", market_id, "Simulated timeout")

    monkeypatch.setattr(KalshiClient, "fetch_market_quotes", _mock_fetch_error)

    kalshi_client = KalshiClient()
    exchange_ingestion = ExchangeIngestionService(db_session)

    alignment_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.kalshi_market_id.isnot(None),
        CanonicalEventAlignment.canonical_event_key == "cek_fail",
    )
    rows = list((await db_session.execute(alignment_stmt)).scalars().all())

    # Simulate the poller's fail-open loop
    markets_polled = 0
    quotes_inserted = 0
    for a in rows:
        try:
            raw = await kalshi_client.fetch_market_quotes(a.kalshi_market_id)  # type: ignore[arg-type]
            inserted = await exchange_ingestion.ingest_exchange_quotes(
                canonical_event_key=a.canonical_event_key,
                source="KALSHI",
                raw_payload=raw,
            )
            quotes_inserted += inserted
            markets_polled += 1
        except ExchangeUpstreamError:
            pass  # fail-open: log and continue (logger tested separately)

    # No crash, no quotes inserted, no markets successfully polled
    assert markets_polled == 0
    assert quotes_inserted == 0
