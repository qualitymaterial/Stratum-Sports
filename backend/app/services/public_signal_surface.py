import logging
from typing import Any

from sqlalchemy.sql import Select

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

STRUCTURAL_CORE_SIGNAL_TYPE = "KEY_CROSS"
STRUCTURAL_CORE_MARKET = "spreads"
STRUCTURAL_CORE_DISPLAY_TYPE = "STRUCTURAL THRESHOLD EVENT"
STRUCTURAL_CORE_MIN_STRENGTH = 55
STRUCTURAL_CORE_MIN_SAMPLES = 15

_logged_missing_fields: set[str] = set()


def public_structural_core_mode_enabled() -> bool:
    return bool(settings.public_structural_core_mode)


def signal_display_type(signal_type: str | None) -> str:
    normalized = str(signal_type or "")
    if normalized == STRUCTURAL_CORE_SIGNAL_TYPE:
        return STRUCTURAL_CORE_DISPLAY_TYPE
    if normalized == "EXCHANGE_DIVERGENCE":
        return "EXCHANGE DIVERGENCE"
    return normalized


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _log_missing_filter_field(*, context: str, field_name: str) -> None:
    marker = f"{context}:{field_name}"
    if marker in _logged_missing_fields:
        return
    _logged_missing_fields.add(marker)
    logger.info(
        "Public structural core filter skipped for missing field",
        extra={"context": context, "field": field_name, "todo": "add schema field or remove filter"},
    )


def apply_structural_core_query_filters(
    stmt: Select,
    *,
    signal_model: Any,
    context: str,
    min_strength: int | None = None,
) -> Select:
    if not public_structural_core_mode_enabled():
        return stmt

    if hasattr(signal_model, "signal_type"):
        stmt = stmt.where(signal_model.signal_type == STRUCTURAL_CORE_SIGNAL_TYPE)
    else:
        _log_missing_filter_field(context=context, field_name="signal_type")

    if hasattr(signal_model, "market"):
        stmt = stmt.where(signal_model.market == STRUCTURAL_CORE_MARKET)
    else:
        _log_missing_filter_field(context=context, field_name="market")

    if hasattr(signal_model, "strength_score"):
        floor = STRUCTURAL_CORE_MIN_STRENGTH
        parsed = _coerce_int(min_strength)
        if parsed is not None:
            floor = max(floor, parsed)
        stmt = stmt.where(signal_model.strength_score >= floor)
    else:
        _log_missing_filter_field(context=context, field_name="strength_score")

    _log_missing_filter_field(context=context, field_name="min_samples")
    return stmt


def is_structural_core_visible(
    *,
    signal_type: Any,
    market: Any,
    strength_score: Any,
    min_samples: Any,
    context: str,
) -> bool:
    if not public_structural_core_mode_enabled():
        return True

    if signal_type is None:
        _log_missing_filter_field(context=context, field_name="signal_type")
    elif str(signal_type) != STRUCTURAL_CORE_SIGNAL_TYPE:
        return False

    if market is None:
        _log_missing_filter_field(context=context, field_name="market")
    elif str(market).lower() != STRUCTURAL_CORE_MARKET:
        return False

    strength_value = _coerce_int(strength_score)
    if strength_value is None:
        _log_missing_filter_field(context=context, field_name="strength_score")
    elif strength_value < STRUCTURAL_CORE_MIN_STRENGTH:
        return False

    sample_value = _coerce_int(min_samples)
    if sample_value is None:
        _log_missing_filter_field(context=context, field_name="min_samples")
    elif sample_value < STRUCTURAL_CORE_MIN_SAMPLES:
        return False

    return True
