"""Regime detection configuration, decoupled from global Settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeConfig:
    """All tuning knobs for the 2-state regime detector."""

    enabled: bool = False
    lookback_minutes: int = 30
    min_snapshots: int = 3

    # HMM Gaussian emission parameters
    stable_mean: float = 0.20
    stable_var: float = 0.05
    unstable_mean: float = 0.80
    unstable_var: float = 0.15

    # HMM transition probabilities
    p_stable_to_unstable: float = 0.10
    p_unstable_to_stable: float = 0.20

    # Prior probability of starting in the stable state
    initial_stable_prob: float = 0.70

    model_version: str = "v1"


def regime_config_from_settings(settings: object) -> RegimeConfig:
    """Build a RegimeConfig from the application Settings object."""
    return RegimeConfig(
        enabled=getattr(settings, "regime_detection_enabled", False),
    )
