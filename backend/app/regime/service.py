"""Regime detection service — orchestrates feature extraction, HMM inference,
metadata attachment, and optional snapshot persistence."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.regime_snapshot import RegimeSnapshot
from app.models.signal import Signal
from app.regime.config import RegimeConfig
from app.regime.features import extract_features
from app.regime.hmm import TwoStateGaussianHMM
from app.regime.metrics import log_regime_cycle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegimeOutput:
    """Public result for a single (event_id, market)."""

    regime_label: str
    regime_probability: float
    transition_risk: float
    stability_score: float
    model_version: str
    snapshots_used: int


class RegimeService:
    """Computes 2-state market regime per (event_id, market)."""

    def __init__(self, db: AsyncSession, config: RegimeConfig) -> None:
        self._db = db
        self._config = config
        self._hmm = TwoStateGaussianHMM(
            stable_mean=config.stable_mean,
            stable_var=config.stable_var,
            unstable_mean=config.unstable_mean,
            unstable_var=config.unstable_var,
            p_stable_to_unstable=config.p_stable_to_unstable,
            p_unstable_to_stable=config.p_unstable_to_stable,
            initial_stable_prob=config.initial_stable_prob,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compute_regimes(
        self, event_ids: list[str]
    ) -> dict[tuple[str, str], RegimeOutput]:
        """Compute regime state for all (event_id, market) tuples found
        in recent consensus snapshots.

        Returns an empty dict when the feature flag is off or when there
        is insufficient data.
        """
        if not self._config.enabled or not event_ids:
            return {}

        cutoff = datetime.now(UTC) - timedelta(minutes=self._config.lookback_minutes)

        stmt = (
            select(MarketConsensusSnapshot)
            .where(
                MarketConsensusSnapshot.event_id.in_(event_ids),
                MarketConsensusSnapshot.fetched_at >= cutoff,
            )
            .order_by(MarketConsensusSnapshot.fetched_at.asc())
        )
        rows = list((await self._db.execute(stmt)).scalars().all())

        if not rows:
            return {}

        # Group by (event_id, market)
        grouped: dict[tuple[str, str], list[MarketConsensusSnapshot]] = defaultdict(list)
        for row in rows:
            grouped[(row.event_id, row.market)].append(row)

        results: dict[tuple[str, str], RegimeOutput] = {}
        for key, snapshots in grouped.items():
            features = extract_features(snapshots, min_snapshots=self._config.min_snapshots)
            if features is None:
                continue

            inference = self._hmm.infer([features.composite])
            results[key] = RegimeOutput(
                regime_label=inference.regime_label,
                regime_probability=inference.regime_probability,
                transition_risk=inference.transition_risk,
                stability_score=inference.stability_score,
                model_version=self._config.model_version,
                snapshots_used=features.snapshots_used,
            )

        return results

    async def attach_regime_metadata(
        self,
        signals: list[Signal],
        regimes: dict[tuple[str, str], RegimeOutput],
    ) -> int:
        """Attach regime data to ``signal.metadata_json["regime"]``.

        Mutates the Signal objects in place.  Returns the count of signals enriched.
        """
        enriched = 0
        for signal in signals:
            key = (signal.event_id, signal.market)
            regime = regimes.get(key)
            if regime is None:
                continue
            metadata = dict(signal.metadata_json or {})
            metadata["regime"] = {
                "regime_label": regime.regime_label,
                "regime_probability": regime.regime_probability,
                "transition_risk": regime.transition_risk,
                "stability_score": regime.stability_score,
                "model_version": regime.model_version,
            }
            signal.metadata_json = metadata
            enriched += 1
        return enriched

    async def persist_snapshots(
        self,
        regimes: dict[tuple[str, str], RegimeOutput],
    ) -> int:
        """Persist RegimeSnapshot rows for each computed regime.
        Returns count written."""
        if not regimes:
            return 0

        now = datetime.now(UTC)
        count = 0
        for (event_id, market), regime in regimes.items():
            snapshot = RegimeSnapshot(
                event_id=event_id,
                market=market,
                regime_label=regime.regime_label,
                regime_probability=regime.regime_probability,
                transition_risk=regime.transition_risk,
                stability_score=regime.stability_score,
                model_version=regime.model_version,
                snapshots_used=regime.snapshots_used,
                created_at=now,
            )
            self._db.add(snapshot)
            count += 1

        await self._db.commit()
        return count

    # ------------------------------------------------------------------
    # Convenience: run the full pipeline and log metrics
    # ------------------------------------------------------------------

    async def run(
        self,
        event_ids: list[str],
        signals: list[Signal],
    ) -> tuple[int, int]:
        """Convenience wrapper: compute → attach → persist → log.

        Returns ``(signals_enriched, snapshots_persisted)``.
        """
        t0 = time.monotonic()

        regimes = await self.compute_regimes(event_ids)
        if not regimes:
            return 0, 0

        enriched = await self.attach_regime_metadata(signals, regimes)
        if enriched > 0:
            await self._db.commit()

        persisted = await self.persist_snapshots(regimes)

        duration_ms = int((time.monotonic() - t0) * 1000)
        log_regime_cycle(
            event_ids_processed=len(event_ids),
            regimes_computed=len(regimes),
            signals_enriched=enriched,
            snapshots_persisted=persisted,
            duration_ms=duration_ms,
        )
        return enriched, persisted
