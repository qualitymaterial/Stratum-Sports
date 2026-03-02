from datetime import datetime, UTC
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_lead_lag_event import CrossMarketLeadLagEvent
from app.models.signal import Signal
from app.models.api_partner_webhook import ApiPartnerWebhook
from app.models.exchange_market_snapshot import ExchangeMarketSnapshot
from app.services.kalshi_gating import (
    attach_exchange_liquidity_skew,
    compute_kalshi_skew_gate,
)
from app.services.webhook_delivery import dispatch_signal_to_webhooks


def test_compute_kalshi_skew_gate_null():
    with patch("app.services.kalshi_gating.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.kalshi_skew_gate_threshold = 0.60
        settings.kalshi_skew_gate_mode = "shadow"
        
        result = compute_kalshi_skew_gate(None)
        
        assert result["kalshi_liquidity_skew"] is None
        assert result["kalshi_skew_bucket"] is None
        assert result["kalshi_gate_pass"] is None
        assert result["kalshi_gate_threshold"] == 0.60
        assert result["kalshi_gate_mode"] == "shadow"

@pytest.mark.parametrize("skew,expected_bucket,expected_pass", [
    (0.50, "A: <0.55", False),
    (0.54, "A: <0.55", False),
    (0.56, "B: 0.55-0.60", False),
    (0.60, "C: 0.60-0.65", True),
    (0.64, "C: 0.60-0.65", True),
    (0.66, "D: >0.65", True),
])
def test_compute_kalshi_skew_gate_buckets(skew, expected_bucket, expected_pass):
    with patch("app.services.kalshi_gating.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.kalshi_skew_gate_threshold = 0.60
        settings.kalshi_skew_gate_mode = "enforce"
        
        result = compute_kalshi_skew_gate(skew)
        
        assert result["kalshi_liquidity_skew"] == skew
        assert result["kalshi_skew_bucket"] == expected_bucket
        assert result["kalshi_gate_pass"] is expected_pass


@pytest.mark.asyncio
async def test_webhook_delivery_shadow_mode():
    # Setup mock signals + webhooks
    db = AsyncMock()
    webhook = ApiPartnerWebhook(id=uuid.uuid4(), url="http://test.com", is_active=True)
    # For SQLAlchemy .scalars().all() chain mock
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = [webhook]
    db.execute.return_value = db_result
    
    signal_pass = Signal(
        id=uuid.uuid4(), event_id="ev1", market="spreads", signal_type="steam", direction="home",
        from_value=1.0, to_value=2.0, window_minutes=5, velocity_minutes=1.0, strength_score=90,
        created_at=datetime.now(UTC),
        kalshi_liquidity_skew=0.65, kalshi_gate_pass=True, kalshi_skew_bucket="C", kalshi_gate_threshold=0.6,
    )
    
    signal_fail = Signal(
        id=uuid.uuid4(), event_id="ev2", market="spreads", signal_type="steam", direction="away",
        from_value=1.0, to_value=2.0, window_minutes=5, velocity_minutes=1.0, strength_score=90,
        created_at=datetime.now(UTC),
        kalshi_liquidity_skew=0.50, kalshi_gate_pass=False, kalshi_skew_bucket="A", kalshi_gate_threshold=0.6,
    )
    
    signals = [signal_pass, signal_fail]
    
    with patch("app.services.webhook_delivery._deliver_webhook", new_callable=AsyncMock) as mock_deliver:
        with patch("app.services.webhook_delivery.settings") as mock_settings:
            mock_settings.kalshi_skew_gate_enabled = True
            mock_settings.kalshi_skew_gate_mode = "shadow"
            mock_settings.kalshi_skew_gate_threshold = 0.60
            
            await dispatch_signal_to_webhooks(db, signals)
            
            # Need to sleep slightly since dispatch fires in a create_task
            import asyncio
            await asyncio.sleep(0.01)
            
            # In shadow mode, both signals should be delivered
            assert mock_deliver.call_count == 2
            
            # Verify gate metadata is attached
            calls = mock_deliver.call_args_list
            payload1 = calls[0][0][2]
            assert "kalshi_gate" in payload1
            assert payload1["kalshi_gate"]["kalshi_gate_pass"] is True
            
            payload2 = calls[1][0][2]
            assert payload2["kalshi_gate"]["kalshi_gate_pass"] is False


@pytest.mark.asyncio
async def test_webhook_delivery_enforce_mode():
    db = AsyncMock()
    webhook = ApiPartnerWebhook(id=uuid.uuid4(), url="http://test.com", is_active=True)
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = [webhook]
    db.execute.return_value = db_result
    
    signal_pass = Signal(
        id=uuid.uuid4(), event_id="ev1", market="spreads", signal_type="steam", direction="home",
        from_value=1.0, to_value=2.0, window_minutes=5, velocity_minutes=1.0, strength_score=90,
        created_at=datetime.now(UTC),
        kalshi_liquidity_skew=0.65, kalshi_gate_pass=True, kalshi_skew_bucket="C", kalshi_gate_threshold=0.6,
    )
    
    signal_fail = Signal(
        id=uuid.uuid4(), event_id="ev2", market="spreads", signal_type="steam", direction="away",
        from_value=1.0, to_value=2.0, window_minutes=5, velocity_minutes=1.0, strength_score=90,
        created_at=datetime.now(UTC),
        kalshi_liquidity_skew=0.50, kalshi_gate_pass=False, kalshi_skew_bucket="A", kalshi_gate_threshold=0.6,
    )

    signal_null = Signal(
        id=uuid.uuid4(), event_id="ev3", market="totals", signal_type="move", direction="over",
        from_value=210, to_value=212, window_minutes=5, velocity_minutes=1.0, strength_score=90,
        created_at=datetime.now(UTC),
        kalshi_liquidity_skew=None, kalshi_gate_pass=None, kalshi_skew_bucket=None, kalshi_gate_threshold=0.6,
    )
    
    signals = [signal_pass, signal_fail, signal_null]
    
    with patch("app.services.webhook_delivery._deliver_webhook", new_callable=AsyncMock) as mock_deliver:
        with patch("app.services.webhook_delivery.settings") as mock_settings:
            mock_settings.kalshi_skew_gate_enabled = True
            mock_settings.kalshi_skew_gate_mode = "enforce"
            mock_settings.kalshi_skew_gate_threshold = 0.60
            
            await dispatch_signal_to_webhooks(db, signals)
            
            import asyncio
            await asyncio.sleep(0.01)
            
            # In enforce mode, only pass and Null should be delivered
            assert mock_deliver.call_count == 2
            
            delivered_skews = [c[0][2]["kalshi_gate"]["kalshi_liquidity_skew"] for c in mock_deliver.call_args_list]
            assert 0.65 in delivered_skews
            assert None in delivered_skews
            assert 0.50 not in delivered_skews


@pytest.mark.asyncio
async def test_attach_exchange_liquidity_skew_adds_snapshot_and_lead_lag_metadata(
    db_session: AsyncSession,
) -> None:
    alignment = CanonicalEventAlignment(
        canonical_event_key="cek-kalshi-intel",
        sport="basketball",
        league="NBA",
        home_team="BOS",
        away_team="PHI",
        start_time=datetime.now(UTC),
        sportsbook_event_id="ev-kalshi-intel",
        kalshi_market_id="kalshi-intel-1",
        polymarket_market_id=None,
    )
    db_session.add(alignment)

    snapshots = [
        ExchangeMarketSnapshot(
            canonical_event_key="cek-kalshi-intel",
            source="KALSHI",
            market_id="kalshi-intel-1",
            yes_bid_probability=0.51,
            yes_ask_probability=0.53,
            no_bid_probability=0.47,
            no_ask_probability=0.49,
            yes_bid_size=80,
            yes_ask_size=70,
            no_bid_size=90,
            no_ask_size=60,
            volume=100,
            open_interest=1000,
            timestamp=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        ),
        ExchangeMarketSnapshot(
            canonical_event_key="cek-kalshi-intel",
            source="KALSHI",
            market_id="kalshi-intel-1",
            yes_bid_probability=0.52,
            yes_ask_probability=0.54,
            no_bid_probability=0.46,
            no_ask_probability=0.48,
            yes_bid_size=100,
            yes_ask_size=80,
            no_bid_size=70,
            no_ask_size=50,
            volume=120,
            open_interest=1010,
            timestamp=datetime(2026, 3, 1, 12, 2, 0, tzinfo=UTC),
        ),
        ExchangeMarketSnapshot(
            canonical_event_key="cek-kalshi-intel",
            source="KALSHI",
            market_id="kalshi-intel-1",
            yes_bid_probability=0.53,
            yes_ask_probability=0.55,
            no_bid_probability=0.45,
            no_ask_probability=0.47,
            yes_bid_size=110,
            yes_ask_size=90,
            no_bid_size=60,
            no_ask_size=40,
            volume=140,
            open_interest=1020,
            timestamp=datetime(2026, 3, 1, 12, 4, 0, tzinfo=UTC),
        ),
        ExchangeMarketSnapshot(
            canonical_event_key="cek-kalshi-intel",
            source="KALSHI",
            market_id="kalshi-intel-1",
            yes_bid_probability=0.54,
            yes_ask_probability=0.56,
            no_bid_probability=0.44,
            no_ask_probability=0.46,
            yes_bid_size=120,
            yes_ask_size=80,
            no_bid_size=50,
            no_ask_size=50,
            volume=200,
            open_interest=1035,
            timestamp=datetime(2026, 3, 1, 12, 6, 0, tzinfo=UTC),
        ),
    ]
    db_session.add_all(snapshots)
    db_session.add(
        CrossMarketLeadLagEvent(
            canonical_event_key="cek-kalshi-intel",
            threshold_type="SPREAD_THRESHOLD",
            sportsbook_threshold_value=1.5,
            exchange_probability_threshold=0.55,
            lead_source="EXCHANGE",
            sportsbook_break_timestamp=datetime(2026, 3, 1, 12, 6, 30, tzinfo=UTC),
            exchange_break_timestamp=datetime(2026, 3, 1, 12, 5, 43, tzinfo=UTC),
            lag_seconds=47,
            created_at=datetime(2026, 3, 1, 12, 7, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    signal = Signal(
        id=uuid.uuid4(),
        event_id="ev-kalshi-intel",
        market="spreads",
        signal_type="MOVE",
        direction="home",
        from_value=-2.5,
        to_value=-3.0,
        window_minutes=5,
        velocity_minutes=1.0,
        strength_score=82,
        metadata_json={},
        created_at=datetime.now(UTC),
    )

    await attach_exchange_liquidity_skew(db_session, [signal])

    meta = signal.metadata_json
    assert meta["exchange_liquidity_skew"] == pytest.approx(0.55, rel=1e-6)
    assert meta["exchange_top_book_spread_bps"] == pytest.approx(200.0, rel=1e-6)
    assert meta["exchange_depth_imbalance"] == pytest.approx(0.3333, rel=1e-3)
    assert meta["exchange_trade_flow_volume_delta"] == 60
    assert meta["exchange_trade_flow_rate_per_min"] == pytest.approx(30.0, rel=1e-6)
    assert meta["exchange_trade_flow_burst_score"] == pytest.approx(3.0, rel=1e-6)
    assert meta["exchange_lead_source"] == "EXCHANGE"
    assert meta["exchange_lead_lag_seconds"] == 47
