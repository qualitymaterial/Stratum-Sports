from datetime import UTC, datetime, timedelta

import httpx

from app.services import odds_api
from app.services.odds_api import OddsApiClient


def _reset_circuit_state() -> None:
    OddsApiClient._consecutive_failures = 0
    OddsApiClient._circuit_open_until = None


async def test_fetch_nba_odds_retries_and_recovers(monkeypatch) -> None:
    _reset_circuit_state()
    calls = {"count": 0}

    async def fake_get(self, url, params=None):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ConnectError("temporary failure", request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            json=[],
            headers={"x-requests-remaining": "1000", "x-requests-used": "10"},
            request=httpx.Request("GET", url),
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(odds_api.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_attempts", 3)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_retry_backoff_max_seconds", 0.01)
    monkeypatch.setattr(odds_api.settings, "odds_api_circuit_failures_to_open", 10)

    result = await OddsApiClient().fetch_nba_odds()
    assert calls["count"] == 3
    assert result.events == []
    assert OddsApiClient._consecutive_failures == 0
    assert OddsApiClient._circuit_open_until is None


async def test_fetch_nba_odds_skips_when_circuit_open(monkeypatch) -> None:
    _reset_circuit_state()
    OddsApiClient._consecutive_failures = 3
    OddsApiClient._circuit_open_until = datetime.now(UTC) + timedelta(seconds=60)
    called = {"value": False}

    async def fake_get(self, url, params=None):  # type: ignore[no-untyped-def]
        called["value"] = True
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(odds_api.settings, "odds_api_key", "test-key")

    result = await OddsApiClient().fetch_nba_odds()
    assert result.events == []
    assert called["value"] is False

    _reset_circuit_state()
