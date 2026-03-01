"""
Tests for Odds API response parsing and the ingestion normalizer.

Covers edge cases that are NOT handled by test_odds_api_resilience.py:
- Non-list (dict / unexpected) payloads from the API
- Missing rate-limit headers
- Missing ODDS_API_KEY short-circuit
- Partial / malformed event structures in normalize_event_odds_rows
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.services import odds_api
from app.services.odds_api import (
    OddsApiClient,
    _extract_history_events,
    _parse_header_int,
    _parse_iso_datetime,
)
from app.services.ingestion import normalize_event_odds_rows


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _reset_circuit_state() -> None:
    OddsApiClient._consecutive_failures = 0
    OddsApiClient._circuit_open_until = None


def _ok_response(payload, *, headers: dict | None = None):
    """Build a fake httpx.Response with optional custom headers."""
    default_headers = {
        "x-requests-remaining": "500",
        "x-requests-used": "20",
        "x-requests-last": "5",
    }
    if headers is not None:
        default_headers.update(headers)
    return httpx.Response(
        200,
        json=payload,
        headers=default_headers,
        request=httpx.Request("GET", "https://api.the-odds-api.com/v4/sports/nba/odds"),
    )


# ---------------------------------------------------------------------------
# 1) _parse_header_int edge cases
# ---------------------------------------------------------------------------

def test_parse_header_int_valid():
    headers = httpx.Headers({"x-requests-remaining": "42"})
    assert _parse_header_int(headers, "x-requests-remaining") == 42


def test_parse_header_int_missing_key():
    headers = httpx.Headers({})
    assert _parse_header_int(headers, "x-requests-remaining") is None


def test_parse_header_int_non_numeric():
    headers = httpx.Headers({"x-requests-remaining": "not-a-number"})
    assert _parse_header_int(headers, "x-requests-remaining") is None


# ---------------------------------------------------------------------------
# 2) _parse_iso_datetime edge cases
# ---------------------------------------------------------------------------

def test_parse_iso_datetime_none():
    assert _parse_iso_datetime(None) is None


def test_parse_iso_datetime_empty_string():
    assert _parse_iso_datetime("") is None


def test_parse_iso_datetime_garbage():
    assert _parse_iso_datetime("not-a-date") is None


def test_parse_iso_datetime_valid_z():
    result = _parse_iso_datetime("2026-03-01T12:00:00Z")
    assert result is not None
    assert result.tzinfo is not None


def test_parse_iso_datetime_valid_offset():
    result = _parse_iso_datetime("2026-03-01T12:00:00+05:00")
    assert result is not None
    assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# 3) _extract_history_events (covers dict / nested payloads)
# ---------------------------------------------------------------------------

def test_extract_history_events_from_list():
    payload = [{"id": "e1", "bookmakers": []}, {"id": "e2", "bookmakers": []}]
    events, ts, prev, nxt = _extract_history_events(payload)
    assert len(events) == 2


def test_extract_history_events_from_dict_data_key():
    payload = {"data": [{"id": "e1"}], "timestamp": "2026-03-01T00:00:00Z"}
    events, ts, prev, nxt = _extract_history_events(payload)
    assert len(events) == 1
    assert ts is not None


def test_extract_history_events_from_dict_events_key():
    payload = {"events": [{"id": "e1"}]}
    events, ts, prev, nxt = _extract_history_events(payload)
    assert len(events) == 1


def test_extract_history_events_single_event_dict():
    """When the API returns a single event object (not wrapped in a list)."""
    payload = {"id": "abc", "bookmakers": []}
    events, ts, prev, nxt = _extract_history_events(payload)
    assert len(events) == 1
    assert events[0]["id"] == "abc"


def test_extract_history_events_unexpected_type():
    events, ts, prev, nxt = _extract_history_events("garbage string")
    assert events == []


# ---------------------------------------------------------------------------
# 4) fetch_nba_odds – non-list payload handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_empty_events_on_dict_payload(monkeypatch):
    """API returns a dict instead of a list; should yield empty events, not crash."""
    _reset_circuit_state()

    async def fake_get(self, url, params=None):
        return _ok_response({"message": "unexpected format"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 1)

    result = await OddsApiClient().fetch_nba_odds()
    assert result.events == []
    assert result.requests_remaining == 500


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_missing_api_key(monkeypatch):
    """When ODDS_API_KEY is empty, fetch should short-circuit immediately."""
    _reset_circuit_state()
    called = {"value": False}

    async def fake_get(self, url, params=None):
        called["value"] = True
        return _ok_response([])

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "")

    result = await OddsApiClient().fetch_nba_odds()
    assert result.events == []
    assert called["value"] is False  # should never hit the network


@pytest.mark.asyncio
async def test_fetch_handles_missing_rate_limit_headers(monkeypatch):
    """API response without rate-limit headers should still parse OK."""
    _reset_circuit_state()

    async def fake_get(self, url, params=None):
        return httpx.Response(
            200,
            json=[{"id": "evt1", "bookmakers": []}],
            headers={},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 1)

    result = await OddsApiClient().fetch_nba_odds()
    assert len(result.events) == 1
    assert result.requests_remaining is None
    assert result.requests_used is None


# ---------------------------------------------------------------------------
# 5) normalize_event_odds_rows – partial / malformed event structures
# ---------------------------------------------------------------------------

_FETCHED_AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def test_normalize_event_missing_bookmakers():
    """Event with no 'bookmakers' key → should produce zero rows."""
    event = {
        "id": "e1",
        "commence_time": "2026-03-01T19:00:00Z",
        "home_team": "Team A",
        "away_team": "Team B",
    }
    rows = normalize_event_odds_rows(event, fetched_at=_FETCHED_AT)
    assert rows == []


def test_normalize_event_empty_outcomes():
    """Bookmaker has a market but outcomes list is empty → zero rows."""
    event = {
        "id": "e2",
        "commence_time": "2026-03-01T19:00:00Z",
        "home_team": "A",
        "away_team": "B",
        "bookmakers": [
            {"key": "fanduel", "markets": [{"key": "spreads", "outcomes": []}]}
        ],
    }
    rows = normalize_event_odds_rows(event, fetched_at=_FETCHED_AT)
    assert rows == []


def test_normalize_event_skips_unknown_market():
    """Markets not in the allowed_markets set should be dropped."""
    event = {
        "id": "e3",
        "commence_time": "2026-03-01T19:00:00Z",
        "home_team": "A",
        "away_team": "B",
        "bookmakers": [
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "player_props",
                        "outcomes": [{"name": "o", "price": -110, "point": 5.5}],
                    }
                ],
            }
        ],
    }
    rows = normalize_event_odds_rows(event, fetched_at=_FETCHED_AT)
    assert rows == []


def test_normalize_event_skips_outcome_missing_price():
    """Outcomes that lack a 'price' should be silently ignored."""
    event = {
        "id": "e4",
        "commence_time": "2026-03-01T19:00:00Z",
        "home_team": "A",
        "away_team": "B",
        "bookmakers": [
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [{"name": "A", "point": -3.5}],  # no 'price'
                    }
                ],
            }
        ],
    }
    rows = normalize_event_odds_rows(event, fetched_at=_FETCHED_AT)
    assert rows == []


def test_normalize_event_happy_path():
    """A well-formed event should normalize correctly."""
    event = {
        "id": "e5",
        "sport_key": "basketball_nba",
        "commence_time": "2026-03-01T19:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Home", "price": -110, "point": -3.5},
                            {"name": "Away", "price": -110, "point": 3.5},
                        ],
                    },
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Home", "price": -150},
                            {"name": "Away", "price": 130},
                        ],
                    },
                ],
            }
        ],
    }
    rows = normalize_event_odds_rows(event, fetched_at=_FETCHED_AT)
    assert len(rows) == 4
    spread_rows = [r for r in rows if r.market == "spreads"]
    h2h_rows = [r for r in rows if r.market == "h2h"]
    assert len(spread_rows) == 2
    assert len(h2h_rows) == 2
    # spreads should have line values; h2h should not
    assert spread_rows[0].line == -3.5
    assert h2h_rows[0].line is None
