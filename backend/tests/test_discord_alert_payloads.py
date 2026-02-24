from datetime import UTC, datetime, timedelta

from app.services import discord_alerts as discord_alerts_service
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.signal import Signal
from app.services.alert_rules import evaluate_signal_for_connection
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


def _move_signal() -> Signal:
    return Signal(
        event_id="event_discord_move",
        market="spreads",
        signal_type="MOVE",
        direction="UP",
        from_value=-3.5,
        to_value=-2.5,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=8,
        velocity_minutes=2.5,
        strength_score=78,
        metadata_json={"outcome_name": "BOS"},
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


def test_enriched_move_alert_includes_intelligence_block() -> None:
    signal = _move_signal()
    signal.composite_score = 83
    signal.time_bucket = "PRETIP"
    signal.minutes_to_tip = 42
    signal.velocity = 0.025
    signal.acceleration = 0.004

    game = Game(
        event_id=signal.event_id,
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=2),
        home_team="NYK",
        away_team="BOS",
    )

    message = _format_alert(signal, game)

    assert "Composite Score: 83 (High)" in message
    assert "Timing: PRETIP (42m to tip)" in message
    assert "Velocity: 0.025" in message
    assert "Acceleration: 0.004" in message
    assert "— Intelligence —" in message


def test_non_enriched_alert_excludes_intelligence_block_even_with_optional_fields() -> None:
    signal = _move_signal()
    signal.composite_score = None
    signal.time_bucket = "LATE"
    signal.minutes_to_tip = 180
    signal.velocity = 0.033
    signal.acceleration = 0.006

    game = Game(
        event_id=signal.event_id,
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=2),
        home_team="NYK",
        away_team="BOS",
    )
    message = _format_alert(signal, game)

    assert "Composite Score:" not in message
    assert "Timing:" not in message
    assert "\nVelocity: 0.033" not in message
    assert "Acceleration:" not in message
    assert "— Intelligence —" not in message


def test_enriched_alert_omits_acceleration_when_missing() -> None:
    signal = _move_signal()
    signal.composite_score = 60
    signal.time_bucket = "LATE"
    signal.minutes_to_tip = 180
    signal.velocity = 0.031
    signal.acceleration = None

    message = _format_alert(signal, None)
    assert "Composite Score: 60 (Medium)" in message
    assert "Timing: LATE (180m to tip)" in message
    assert "Velocity: 0.031" in message
    assert "Acceleration:" not in message


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


def test_alert_rules_apply_books_and_dispersion_thresholds() -> None:
    connection = _connection()
    connection.thresholds_json = {
        "min_books_affected": 4,
        "max_dispersion": 0.5,
        "cooldown_minutes": 10,
    }
    signal = _dislocation_signal("spreads")
    signal.books_affected = 3
    signal.metadata_json["dispersion"] = 0.4

    allowed, reason, _thresholds = evaluate_signal_for_connection(
        connection,
        signal,
        steam_discord_enabled=True,
    )
    assert allowed is False
    assert "books 3 below min 4" in reason

    signal.books_affected = 5
    signal.metadata_json["dispersion"] = 0.8
    allowed, reason, _thresholds = evaluate_signal_for_connection(
        connection,
        signal,
        steam_discord_enabled=True,
    )
    assert allowed is False
    assert "dispersion 0.800 above max 0.500" in reason


def test_alert_rules_respect_cooldown_flag() -> None:
    connection = _connection()
    connection.thresholds_json = {"cooldown_minutes": 15}
    signal = _dislocation_signal("totals")

    allowed, reason, _thresholds = evaluate_signal_for_connection(
        connection,
        signal,
        steam_discord_enabled=True,
        cooldown_active=True,
    )
    assert allowed is False
    assert "cooldown active" in reason.lower()
