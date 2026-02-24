from __future__ import annotations

from app.services.market_dynamics import get_time_bucket


def normalize(value: float, p_low: float, p_high: float) -> float:
    if p_high <= p_low:
        return 0.0
    ratio = (float(value) - float(p_low)) / (float(p_high) - float(p_low))
    return max(0.0, min(1.0, ratio))


def time_bonus_from_bucket(bucket: str) -> float:
    if bucket == "PRETIP":
        return 0.05
    if bucket == "LATE":
        return 0.03
    if bucket == "MID":
        return 0.01
    return 0.0


def compute_composite_score(
    move_strength: float,
    velocity: float | None,
    key_cross_flag: bool,
    minutes_to_tip: float,
) -> int:
    move_strength_norm = normalize(abs(float(move_strength)), p_low=0.25, p_high=2.0)
    velocity_norm = normalize(float(velocity or 0.0), p_low=0.005, p_high=0.05)
    key_cross_bonus = 0.15 if key_cross_flag else 0.0
    bucket = get_time_bucket(float(minutes_to_tip))
    raw = (
        0.55 * move_strength_norm
        + 0.30 * velocity_norm
        + key_cross_bonus
        + time_bonus_from_bucket(bucket)
    )
    return int(round(100.0 * max(0.0, min(1.0, raw))))
