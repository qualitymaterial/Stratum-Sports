from dataclasses import dataclass
from typing import Any

from app.models.discord_connection import DiscordConnection
from app.models.signal import Signal


@dataclass(frozen=True)
class AlertRuleThresholds:
    min_books_affected: int
    max_dispersion: float | None
    cooldown_minutes: int


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_alert_thresholds(connection: DiscordConnection) -> AlertRuleThresholds:
    thresholds = connection.thresholds_json if isinstance(connection.thresholds_json, dict) else {}
    min_books = max(1, _coerce_int(thresholds.get("min_books_affected"), 1))
    cooldown_minutes = max(0, _coerce_int(thresholds.get("cooldown_minutes"), 15))
    max_dispersion = _coerce_float(thresholds.get("max_dispersion"))
    if max_dispersion is not None and max_dispersion < 0:
        max_dispersion = None

    return AlertRuleThresholds(
        min_books_affected=min_books,
        max_dispersion=max_dispersion,
        cooldown_minutes=cooldown_minutes,
    )


def evaluate_signal_for_connection(
    connection: DiscordConnection,
    signal: Signal,
    *,
    steam_discord_enabled: bool,
    cooldown_active: bool = False,
) -> tuple[bool, str, AlertRuleThresholds]:
    thresholds = parse_alert_thresholds(connection)
    if not connection.is_enabled:
        return False, "Hidden: alerts disabled.", thresholds
    if signal.strength_score < connection.min_strength:
        return False, f"Hidden: strength {signal.strength_score} below min {connection.min_strength}.", thresholds
    if signal.books_affected < thresholds.min_books_affected:
        return (
            False,
            f"Hidden: books {signal.books_affected} below min {thresholds.min_books_affected}.",
            thresholds,
        )

    if thresholds.max_dispersion is not None:
        dispersion = _coerce_float((signal.metadata_json or {}).get("dispersion"))
        if dispersion is not None and dispersion > thresholds.max_dispersion:
            return (
                False,
                f"Hidden: dispersion {dispersion:.3f} above max {thresholds.max_dispersion:.3f}.",
                thresholds,
            )

    if signal.signal_type == "STEAM":
        if not steam_discord_enabled:
            return False, "Hidden: STEAM alerts disabled globally.", thresholds
        if signal.market == "spreads":
            allowed = connection.alert_spreads
        elif signal.market == "totals":
            allowed = connection.alert_totals
        else:
            allowed = connection.alert_multibook
        if not allowed:
            return False, f"Hidden: {signal.market} alerts disabled.", thresholds
    elif signal.signal_type == "DISLOCATION":
        if signal.market == "spreads" and not connection.alert_spreads:
            return False, "Hidden: spread alerts disabled.", thresholds
        if signal.market == "totals" and not connection.alert_totals:
            return False, "Hidden: total alerts disabled.", thresholds
        if signal.market == "h2h" and not connection.alert_multibook:
            return False, "Hidden: multibook alerts disabled.", thresholds
    elif signal.signal_type == "MULTIBOOK_SYNC":
        if not connection.alert_multibook:
            return False, "Hidden: multibook alerts disabled.", thresholds
    elif signal.market == "spreads":
        if not connection.alert_spreads:
            return False, "Hidden: spread alerts disabled.", thresholds
    elif signal.market == "totals":
        if not connection.alert_totals:
            return False, "Hidden: total alerts disabled.", thresholds

    if cooldown_active and thresholds.cooldown_minutes > 0:
        return False, "Hidden: cooldown active.", thresholds

    return True, "Sent: met alert rules.", thresholds
