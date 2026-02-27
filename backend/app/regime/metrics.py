"""Structured logging helpers for regime detection."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_regime_cycle(
    *,
    event_ids_processed: int,
    regimes_computed: int,
    signals_enriched: int,
    snapshots_persisted: int,
    duration_ms: int,
) -> None:
    logger.info(
        "Regime detection cycle completed",
        extra={
            "regime_event_ids_processed": event_ids_processed,
            "regime_regimes_computed": regimes_computed,
            "regime_signals_enriched": signals_enriched,
            "regime_snapshots_persisted": snapshots_persisted,
            "regime_duration_ms": duration_ms,
        },
    )
