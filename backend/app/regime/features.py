"""Extract regime features from MarketConsensusSnapshot time series."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.market_consensus_snapshot import MarketConsensusSnapshot

# Feature weights for the composite scalar
_W_DISPERSION = 0.35
_W_VELOCITY = 0.30
_W_TREND = 0.20
_W_BOOKS = 0.15

# Normalisation reference ceilings (domain-informed)
_MAX_DISPERSION = 50.0  # price-unit dispersion ceiling
_MAX_VELOCITY = 5.0  # consensus line movement per minute
_MAX_BOOKS_CV = 1.0  # coefficient of variation ceiling for books_count


@dataclass(frozen=True)
class RegimeFeatures:
    """Feature vector extracted from a window of consensus snapshots."""

    dispersion_mean: float
    price_velocity: float
    dispersion_trend: float
    books_stability: float
    composite: float
    snapshots_used: int


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _std(values: list[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def extract_features(
    snapshots: list[MarketConsensusSnapshot],
    min_snapshots: int = 3,
) -> RegimeFeatures | None:
    """Compute a composite volatility feature from time-ordered consensus snapshots.

    *snapshots* must all share the same ``(event_id, market)`` and be sorted by
    ``fetched_at`` ascending.  Outcomes are aggregated — regime is per-market,
    not per-outcome.

    Returns ``None`` when fewer than *min_snapshots* are available.
    """
    if len(snapshots) < min_snapshots:
        return None

    # --- 1. Dispersion mean ---
    dispersions = [s.dispersion for s in snapshots if s.dispersion is not None]
    disp_mean = _mean(dispersions) if dispersions else 0.0
    norm_dispersion = _clamp01(disp_mean / _MAX_DISPERSION)

    # --- 2. Price velocity ---
    # Use consensus_line when available, fall back to consensus_price.
    values: list[tuple[float, float]] = []  # (epoch_minutes, value)
    for s in snapshots:
        val = s.consensus_line if s.consensus_line is not None else s.consensus_price
        if val is not None:
            epoch_min = s.fetched_at.timestamp() / 60.0
            values.append((epoch_min, val))

    if len(values) >= 2:
        first_t, first_v = values[0]
        last_t, last_v = values[-1]
        dt = last_t - first_t
        velocity = abs(last_v - first_v) / dt if dt > 0 else 0.0
    else:
        velocity = 0.0
    norm_velocity = _clamp01(velocity / _MAX_VELOCITY)

    # --- 3. Dispersion trend (slope direction) ---
    # Positive slope = dispersion increasing = more unstable.
    if len(dispersions) >= 2:
        first_half = dispersions[: len(dispersions) // 2]
        second_half = dispersions[len(dispersions) // 2 :]
        trend = _mean(second_half) - _mean(first_half)
        # Normalise: trend / disp_mean gives relative change; clamp to [0, 1].
        if disp_mean > 0:
            norm_trend = _clamp01(trend / disp_mean)
        else:
            norm_trend = _clamp01(trend / _MAX_DISPERSION)
    else:
        norm_trend = 0.0

    # --- 4. Books stability ---
    book_counts = [float(s.books_count) for s in snapshots]
    mean_books = _mean(book_counts)
    if mean_books > 0:
        cv = _std(book_counts) / mean_books  # coefficient of variation
    else:
        cv = 0.0
    norm_books = _clamp01(cv / _MAX_BOOKS_CV)

    # --- Composite ---
    composite = (
        _W_DISPERSION * norm_dispersion
        + _W_VELOCITY * norm_velocity
        + _W_TREND * norm_trend
        + _W_BOOKS * norm_books
    )
    composite = _clamp01(composite)

    return RegimeFeatures(
        dispersion_mean=round(disp_mean, 4),
        price_velocity=round(velocity, 4),
        dispersion_trend=round(norm_trend, 4),
        books_stability=round(norm_books, 4),
        composite=round(composite, 6),
        snapshots_used=len(snapshots),
    )
