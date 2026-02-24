from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable


Point = tuple[datetime, float]


def _as_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _extract_value(snapshot: Any, candidates: tuple[str, ...]) -> Any:
    if isinstance(snapshot, dict):
        for name in candidates:
            if name in snapshot:
                return snapshot.get(name)
        return None
    for name in candidates:
        if hasattr(snapshot, name):
            return getattr(snapshot, name)
    return None


def get_time_bucket(minutes_to_tip: float) -> str:
    if minutes_to_tip <= 60:
        return "PRETIP"
    if minutes_to_tip <= 360:
        return "LATE"
    if minutes_to_tip <= 1440:
        return "MID"
    return "OPEN"


def compute_velocity(points: list[Point]) -> float | None:
    if len(points) < 2:
        return None
    ordered = sorted(points, key=lambda item: item[0])
    first_ts, first_line = ordered[0]
    last_ts, last_line = ordered[-1]
    minutes_elapsed = (last_ts - first_ts).total_seconds() / 60.0
    if minutes_elapsed <= 0:
        return None
    return abs(float(last_line) - float(first_line)) / minutes_elapsed


def compute_acceleration(points: list[Point]) -> float | None:
    if len(points) < 4:
        return None
    ordered = sorted(points, key=lambda item: item[0])
    mid_idx = len(ordered) // 2
    first_half = ordered[:mid_idx]
    second_half = ordered[mid_idx:]
    if len(first_half) < 2 or len(second_half) < 2:
        return None

    v1 = compute_velocity(first_half)
    v2 = compute_velocity(second_half)
    if v1 is None or v2 is None:
        return None
    return v2 - v1


def build_line_series_from_snapshots(
    snapshots: Iterable[Any],
    *,
    line_attr_candidates: tuple[str, ...] = ("line",),
    ts_attr_candidates: tuple[str, ...] = ("fetched_at",),
) -> list[Point]:
    points_with_order: list[tuple[datetime, int, float]] = []
    for idx, snapshot in enumerate(snapshots):
        line_raw = _extract_value(snapshot, line_attr_candidates)
        ts_raw = _extract_value(snapshot, ts_attr_candidates)

        ts = _as_utc_datetime(ts_raw)
        if ts is None or line_raw is None:
            continue

        try:
            line_value = float(line_raw)
        except (TypeError, ValueError):
            continue

        points_with_order.append((ts, idx, line_value))

    points_with_order.sort(key=lambda item: (item[0], item[1]))
    return [(ts, line) for ts, _idx, line in points_with_order]
