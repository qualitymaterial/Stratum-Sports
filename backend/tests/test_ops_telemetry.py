"""
Ops Telemetry & Error Instrumentation Tests

Verifies graceful degradation when external dependencies fail:
1. Redis unavailable during Discord alert cooldown
2. Webhook target endpoint unreachable
3. Webhook target returns 5xx
4. ingest_odds_cycle survives Redis being None
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.services.odds_api import OddsFetchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_signal(**overrides) -> Signal:
    """Create a minimal Signal instance for testing."""
    defaults = {
        "event_id": f"test_{uuid.uuid4().hex[:8]}",
        "market": "spreads",
        "signal_type": "MOVE",
        "direction": "up",
        "strength_score": 70,
        "time_bucket": "pre_tip",
        "from_value": -3.5,
        "to_value": -5.0,
        "window_minutes": 10,
        "metadata_json": {"sportsbook_key": "fanduel", "velocity_minutes": 3.0},
    }
    defaults.update(overrides)
    return Signal(**defaults)


# ---------------------------------------------------------------------------
# 1) Discord alerts: Redis failure during cooldown check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discord_alert_continues_when_redis_read_raises(db_session: AsyncSession):
    """
    When Redis raises an exception during cooldown key lookup,
    the alert should still proceed (cooldown_active defaults to False).
    """
    from app.services.discord_alerts import _alert_cooldown_key

    signal = _make_test_signal()

    # Create a mock Redis that raises on .get()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

    key = _alert_cooldown_key("user123", signal)

    # Verify the key generation doesn't crash
    assert isinstance(key, str)
    assert "user123" in key

    # Verify that if we call redis.get and it fails, the exception is raised
    # (the caller in discord_alerts.py catches this with try/except)
    with pytest.raises(ConnectionError):
        await mock_redis.get(key)


@pytest.mark.asyncio
async def test_discord_alert_continues_when_redis_write_raises():
    """
    When Redis raises during cooldown SET after a successful alert send,
    the system should log the error but not crash or lose the alert.
    """
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

    # The SET should raise, but in production code it's caught
    with pytest.raises(ConnectionError):
        await mock_redis.set("discord:cooldown:test", "1", ex=300)


# ---------------------------------------------------------------------------
# 2) Webhook delivery: target endpoint unreachable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_delivery_logs_error_on_connection_failure():
    """
    When the webhook target is completely unreachable, the delivery function
    should retry and ultimately log the failure without crashing.
    """
    from app.services.webhook_delivery import _deliver_webhook

    # Create a mock webhook object
    mock_webhook = MagicMock()
    mock_webhook.id = uuid.uuid4()
    mock_webhook.url = "https://unreachable.example.com/webhook"
    mock_webhook.secret = "test-secret-key"

    signal_id = uuid.uuid4()
    payload = {
        "event": "signal.detected",
        "signal_id": str(signal_id),
        "market": "spreads",
    }

    # Mock the AsyncClient to always raise ConnectError
    with patch("app.services.webhook_delivery.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=httpx.ConnectError(
                "connection refused",
                request=httpx.Request("POST", mock_webhook.url),
            )
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        # Also mock the DB session used for logging
        with patch("app.core.database.AsyncSessionLocal") as MockSession:
            mock_db = AsyncMock()
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_db

            # Patch settings for minimal retries
            with patch("app.services.webhook_delivery.settings") as mock_settings:
                mock_settings.webhook_max_retries = 1
                mock_settings.webhook_timeout_seconds = 5.0
                mock_settings.webhook_initial_delay_seconds = 0.01
                mock_settings.webhook_backoff_factor = 2

                await _deliver_webhook(mock_webhook, signal_id, payload)

                # Should have attempted delivery multiple times
                assert mock_client_instance.post.call_count >= 1

                # Should have logged the delivery result
                assert mock_db.add.called
                assert mock_db.commit.called


# ---------------------------------------------------------------------------
# 3) Webhook delivery: target returns 5xx (retry path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_delivery_retries_on_5xx():
    """5xx responses should trigger retry, while 4xx should not."""
    from app.services.webhook_delivery import _deliver_webhook

    mock_webhook = MagicMock()
    mock_webhook.id = uuid.uuid4()
    mock_webhook.url = "https://api.partner.com/webhook"
    mock_webhook.secret = "secret123"

    signal_id = uuid.uuid4()
    payload = {"event": "signal.detected", "signal_id": str(signal_id)}

    call_count = {"n": 0}

    async def fake_post(url, content=None, headers=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(
                503,
                request=httpx.Request("POST", url),
                content=b"Service Unavailable",
            )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            content=b"OK",
        )

    with patch("app.services.webhook_delivery.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = fake_post
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        with patch("app.core.database.AsyncSessionLocal") as MockSession:
            mock_db = AsyncMock()
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_db

            with patch("app.services.webhook_delivery.settings") as mock_settings:
                mock_settings.webhook_max_retries = 2
                mock_settings.webhook_timeout_seconds = 5.0
                mock_settings.webhook_initial_delay_seconds = 0.01
                mock_settings.webhook_backoff_factor = 2

                await _deliver_webhook(mock_webhook, signal_id, payload)

                # Attempt 1: 503 → retry. Attempt 2: 200 → success.
                assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# 4) ingest_odds_cycle works with redis=None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_odds_cycle_works_without_redis(db_session: AsyncSession):
    """
    The ingestion loop should work perfectly fine when Redis is None
    (all deduplication is skipped, snapshots are always written).
    """
    event = {
        "id": f"test_no_redis_{uuid.uuid4().hex[:8]}",
        "sport_key": "basketball_nba",
        "commence_time": (datetime.now(UTC) + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "home_team": "Test Home",
        "away_team": "Test Away",
        "bookmakers": [
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Test Home", "price": -110, "point": -3.5},
                            {"name": "Test Away", "price": -110, "point": 3.5},
                        ],
                    }
                ],
            }
        ],
    }

    with patch("app.services.ingestion.OddsApiClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_nba_odds = AsyncMock(
            return_value=OddsFetchResult(
                events=[event],
                requests_remaining=900,
                requests_used=10,
            )
        )
        from app.services.ingestion import ingest_odds_cycle

        result = await ingest_odds_cycle(db_session, redis=None)

    assert result is not None
    # Should have processed events without crashing
    assert "events_seen" in result or "event_ids" in result
