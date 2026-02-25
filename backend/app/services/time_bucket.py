from __future__ import annotations

from typing import SupportsFloat


def compute_time_bucket(minutes_to_tip: SupportsFloat | None) -> str:
    """Compute a stable bucket label from minutes_to_tip."""
    if minutes_to_tip is None:
        return "UNKNOWN"

    try:
        value = float(minutes_to_tip)
    except (TypeError, ValueError):
        return "UNKNOWN"

    if value < 0:
        return "INPLAY"
    if value < 30:
        return "PRETIP"
    if value < 120:
        return "LATE"
    if value < 360:
        return "MID"
    return "OPEN"

