"""
Tests for the Odds API retry and backoff logic.

Fills gaps NOT covered by test_odds_api_resilience.py:
- Retry exhaustion (all attempts fail → graceful empty result)
- 429-status handling (retried like network errors)
- Backoff timing verification (exponential delays capped by max)
- Circuit breaker opens after configured consecutive failures
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.services import odds_api
from app.services.odds_api import OddsApiClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_circuit_state() -> None:
    OddsApiClient._consecutive_failures = 0
    OddsApiClient._circuit_open_until = None


# ---------------------------------------------------------------------------
# 1) All retries exhausted → graceful empty result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_retries_exhausted_returns_empty(monkeypatch):
    """When every attempt fails, the client should return an empty result
    instead of raising or crashing the poller."""
    _reset_circuit_state()
    calls = {"count": 0}

    async def always_fail(self, url, params=None):
        calls["count"] += 1
        raise httpx.ReadTimeout(
            "read timed out", request=httpx.Request("GET", url)
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", always_fail)
    monkeypatch.setattr(odds_api.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 3)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 0.05)
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 10)

    result = await OddsApiClient().fetch_nba_odds()

    assert calls["count"] == 3
    assert result.events == []
    # Consecutive failures should have incremented
    assert OddsApiClient._consecutive_failures == 3

    _reset_circuit_state()


# ---------------------------------------------------------------------------
# 2) HTTP 429 (Too Many Requests) is treated as retryable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_is_retried_then_succeeds(monkeypatch):
    """A 429 on the first attempt should be retried and succeed on the next."""
    _reset_circuit_state()
    calls = {"count": 0}

    async def sometimes_429(self, url, params=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                429,
                json={"error": "rate limited"},
                headers={"retry-after": "1"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            json=[{"id": "evt1", "bookmakers": []}],
            headers={"x-requests-remaining": "100", "x-requests-used": "50"},
            request=httpx.Request("GET", url),
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", sometimes_429)
    monkeypatch.setattr(odds_api.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 3)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 0.05)
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 10)

    result = await OddsApiClient().fetch_nba_odds()
    assert calls["count"] == 2
    assert len(result.events) == 1
    assert OddsApiClient._consecutive_failures == 0

    _reset_circuit_state()


# ---------------------------------------------------------------------------
# 3) Backoff timing verification (exponential, capped)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backoff_is_exponential_and_capped(monkeypatch):
    """Verify sleep durations follow exponential backoff with a cap."""
    _reset_circuit_state()
    sleep_values: list[float] = []

    async def always_fail(self, url, params=None):
        raise httpx.ConnectError(
            "connection refused", request=httpx.Request("GET", url)
        )

    async def track_sleep(seconds: float) -> None:
        sleep_values.append(seconds)

    monkeypatch.setattr(httpx.AsyncClient, "get", always_fail)
    monkeypatch.setattr(odds_api.asyncio, "sleep", track_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 4)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 1.0)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 3.0)
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 10)

    await OddsApiClient().fetch_nba_odds()

    # Attempts:  1(fail) → sleep(1)  2(fail) → sleep(2)  3(fail) → sleep(3=cap)  4(fail) → done
    # The last attempt doesn't sleep after failure, it breaks.
    # So we expect 3 sleep calls: [1.0, 2.0, 3.0]
    assert len(sleep_values) == 3
    assert sleep_values[0] == pytest.approx(1.0)
    assert sleep_values[1] == pytest.approx(2.0)
    assert sleep_values[2] == pytest.approx(3.0)  # capped

    _reset_circuit_state()


# ---------------------------------------------------------------------------
# 4) Circuit breaker opens after N consecutive failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_opens_after_consecutive_failures(monkeypatch):
    """After the configured number of failures, circuit should open and skip
    subsequent fetches without hitting the network."""
    _reset_circuit_state()
    net_calls = {"count": 0}

    async def always_fail(self, url, params=None):
        net_calls["count"] += 1
        raise httpx.ConnectError(
            "connection refused", request=httpx.Request("GET", url)
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", always_fail)
    monkeypatch.setattr(odds_api.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 1)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 0.01)
    # Open the circuit after just 2 consecutive failures
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 2)

    # First fetch – 1 network call, 1 failure
    await OddsApiClient().fetch_nba_odds()
    assert net_calls["count"] == 1
    assert OddsApiClient._consecutive_failures == 1
    assert OddsApiClient._circuit_open_until is None

    # Second fetch – 1 network call, opens circuit
    await OddsApiClient().fetch_nba_odds()
    assert net_calls["count"] == 2
    assert OddsApiClient._consecutive_failures == 2
    assert OddsApiClient._circuit_open_until is not None

    # Third fetch – no network call, circuit is open
    await OddsApiClient().fetch_nba_odds()
    assert net_calls["count"] == 2  # unchanged!

    _reset_circuit_state()


# ---------------------------------------------------------------------------
# 5) ConnectError vs ValueError both caught by retry loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_value_error_on_json_decode_is_retried(monkeypatch):
    """If response.json() raises ValueError, it should be caught and retried."""
    _reset_circuit_state()
    calls = {"count": 0}

    async def bad_json_then_ok(self, url, params=None):
        calls["count"] += 1
        if calls["count"] == 1:
            # Return invalid JSON body
            resp = httpx.Response(
                200,
                content=b"not json",
                headers={"content-type": "application/json"},
                request=httpx.Request("GET", url),
            )
            resp.json()  # This will raise ValueError
        return httpx.Response(
            200,
            json=[],
            headers={"x-requests-remaining": "99"},
            request=httpx.Request("GET", url),
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", bad_json_then_ok)
    monkeypatch.setattr(odds_api.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 3)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 10)

    result = await OddsApiClient().fetch_nba_odds()
    assert calls["count"] == 2
    assert result.events == []

    _reset_circuit_state()
