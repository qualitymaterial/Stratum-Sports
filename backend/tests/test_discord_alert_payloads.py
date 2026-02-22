from datetime import UTC, datetime, timedelta

from app.services import discord_alerts as discord_alerts_service
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.signal import Signal
from app.services.discord_alerts import _connection_allows_signal, _format_alert


def _dislocation_signal(market: str = "totals") -> Signal:
    return Signal(
        event_id="event_discord_dislocation",
        market=market,
        signal_type="DISLOCATION",
        direction="DOWN",
        from_value=226.8,
        to_value=224.5,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=1,
        velocity_minutes=0.1,
        strength_score=82,
        metadata_json={
            "book_key": "draftkings",
            "market": market,
            "outcome_name": "Over",
            "book_line": 224.5 if market != "h2h" else None,
            "book_price": -108.0,
            "consensus_line": 226.8 if market != "h2h" else None,
            "consensus_price": -110.0,
            "dispersion": 0.45,
            "books_count": 6,
            "delta": -2.3 if market != "h2h" else -0.0412,
            "delta_type": "line" if market != "h2h" else "implied_prob",
            "lookback_minutes": 10,
        },
    )


def _connection() -> DiscordConnection:
    return DiscordConnection(
        webhook_url="https://discord.example/webhook",
        alert_spreads=True,
        alert_totals=True,
        alert_multibook=True,
        min_strength=60,
        is_enabled=True,
        thresholds_json={},
    )


def _steam_signal(market: str = "spreads") -> Signal:
    return Signal(
        event_id="event_discord_steam",
        market=market,
        signal_type="STEAM",
        direction="DOWN",
        from_value=-3.5,
        to_value=-4.2,
        from_price=None,
        to_price=None,
        window_minutes=3,
        books_affected=4,
        velocity_minutes=3.0,
        strength_score=78,
        metadata_json={
            "market": market,
            "outcome_name": "BOS",
            "direction": "down",
            "books_involved": ["book1", "book2", "book3", "book4"],
            "window_minutes": 3,
            "total_move": -0.7,
            "avg_move": -0.65,
            "start_line": -3.5,
            "end_line": -4.2,
            "speed": 0.233333,
        },
    )


def test_dislocation_alert_format_has_required_fields() -> None:
    signal = _dislocation_signal("totals")
    game = Game(
        event_id="event_discord_dislocation",
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=2),
        home_team="NYK",
        away_team="BOS",
    )

    message = _format_alert(signal, game)

    assert "Title: DISLOCATION" in message
    assert "Market: Totals" in message
    assert "Outcome: Over" in message
    assert "Book vs Consensus:" in message
    assert "DRAFTKINGS: 224.5 vs CONS: 226.8 (Δ -2.30)" in message
    assert "Books: 6" in message
    assert "Dispersion: 0.45" in message
    assert "Strength: 82" in message


def test_dislocation_connection_filtering_respects_existing_toggles() -> None:
    connection = _connection()

    spreads_signal = _dislocation_signal("spreads")
    totals_signal = _dislocation_signal("totals")
    h2h_signal = _dislocation_signal("h2h")

    connection.alert_spreads = False
    assert _connection_allows_signal(connection, spreads_signal) is False
    assert _connection_allows_signal(connection, totals_signal) is True

    connection.alert_multibook = False
    assert _connection_allows_signal(connection, h2h_signal) is False


def test_steam_alerts_off_by_default_and_enabled_by_flag(monkeypatch) -> None:
    connection = _connection()
    signal = _steam_signal("spreads")

    monkeypatch.setattr(discord_alerts_service.settings, "steam_discord_enabled", False)
    assert _connection_allows_signal(connection, signal) is False

    monkeypatch.setattr(discord_alerts_service.settings, "steam_discord_enabled", True)
    assert _connection_allows_signal(connection, signal) is True

    connection.alert_spreads = False
    assert _connection_allows_signal(connection, signal) is False
