"""Deterministic cross-market divergence detection between sportsbooks and exchanges."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_divergence_event import CrossMarketDivergenceEvent
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.structural_event import StructuralEvent
from app.services.cross_market_lead_lag import (
    ProbabilityCrossing,
    detect_probability_crossings,
)

logger = logging.getLogger(__name__)

# ── constants ───────────────────────────────────────────────────────
DIVERGENCE_CONFIRM_WINDOW_MINUTES = 10
DIVERGENCE_FRESHNESS_MINUTES = 15
ALIGN_WINDOW_MINUTES = 10
REVERSAL_WINDOW_MINUTES = 30

# Divergence types
DIVERGENCE_ALIGNED = "ALIGNED"
DIVERGENCE_EXCHANGE_LEADS = "EXCHANGE_LEADS"
DIVERGENCE_SPORTSBOOK_LEADS = "SPORTSBOOK_LEADS"
DIVERGENCE_OPPOSED = "OPPOSED"
DIVERGENCE_UNCONFIRMED = "UNCONFIRMED"
DIVERGENCE_REVERTED = "REVERTED"


def _build_idempotency_key(
    canonical_event_key: str,
    divergence_type: str,
    sportsbook_ts: datetime | None,
    exchange_ts: datetime | None,
    sportsbook_threshold: float | None,
    exchange_threshold: float | None,
) -> str:
    """Deterministic idempotency key for a divergence event."""
    sb_iso = sportsbook_ts.isoformat() if sportsbook_ts else "NONE"
    ex_iso = exchange_ts.isoformat() if exchange_ts else "NONE"
    sb_thr = str(sportsbook_threshold) if sportsbook_threshold is not None else "NONE"
    ex_thr = str(exchange_threshold) if exchange_threshold is not None else "NONE"
    return f"{canonical_event_key}|{divergence_type}|{sb_iso}|{ex_iso}|{sb_thr}|{ex_thr}"


class CrossMarketDivergenceService:
    """Detects and persists cross-market divergence events.

    Deterministic rule-set comparing sportsbook structural breaks
    against exchange probability crossings within configurable
    freshness and alignment windows.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compute_divergence(self, canonical_event_key: str) -> int:
        """Run divergence detection pipeline. Returns count of rows inserted."""

        # 1. Resolve alignment
        alignment = await self._load_alignment(canonical_event_key)
        if alignment is None:
            return 0

        now = datetime.now(UTC)
        freshness_cutoff = now - timedelta(minutes=DIVERGENCE_FRESHNESS_MINUTES)

        # 2. Latest sportsbook structural break
        latest_structural = await self._load_latest_structural(
            alignment.sportsbook_event_id, freshness_cutoff
        )

        # 3. Exchange probability crossings
        exchange_quotes = await self._load_exchange_quotes(canonical_event_key, freshness_cutoff)
        crossings = detect_probability_crossings(exchange_quotes) if exchange_quotes else []
        latest_crossing = crossings[-1] if crossings else None

        # 4. Determine divergence type
        result = self._classify_divergence(
            latest_structural, latest_crossing, exchange_quotes, crossings, now
        )
        if result is None:
            return 0

        divergence_type, lead_source, sportsbook_ts, exchange_ts, sb_thr, ex_thr = result

        lag = int(abs((sportsbook_ts - exchange_ts).total_seconds())) if (sportsbook_ts and exchange_ts) else None

        # 5. Idempotent insert
        idempotency_key = _build_idempotency_key(
            canonical_event_key, divergence_type, sportsbook_ts, exchange_ts, sb_thr, ex_thr
        )

        values = {
            "canonical_event_key": canonical_event_key,
            "divergence_type": divergence_type,
            "lead_source": lead_source,
            "sportsbook_threshold_value": sb_thr,
            "exchange_probability_threshold": ex_thr,
            "sportsbook_break_timestamp": sportsbook_ts,
            "exchange_break_timestamp": exchange_ts,
            "lag_seconds": lag,
            "resolved": False,
            "idempotency_key": idempotency_key,
        }

        stmt = pg_insert(CrossMarketDivergenceEvent).values(**values)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_cross_market_divergence_idempotency")
        insert_result = await self.db.execute(stmt)
        inserted = 1 if insert_result.rowcount > 0 else 0

        # 6. Resolution marking
        if inserted > 0:
            await self._resolve_prior_events(canonical_event_key, divergence_type, now)

        await self.db.flush()

        logger.info(
            "Cross-market divergence computed",
            extra={
                "canonical_event_key": canonical_event_key,
                "divergence_type": divergence_type,
                "lead_source": lead_source,
                "lag_seconds": lag,
                "inserted": inserted,
            },
        )
        return inserted

    # ── classification ───────────────────────────────────────────────

    def _classify_divergence(
        self,
        structural: StructuralEvent | None,
        crossing: ProbabilityCrossing | None,
        exchange_quotes: list[ExchangeQuoteEvent],
        crossings: list[ProbabilityCrossing],
        now: datetime,
    ) -> tuple[str, str | None, datetime | None, datetime | None, float | None, float | None] | None:
        """Classify divergence. Returns (type, lead_source, sb_ts, ex_ts, sb_thr, ex_thr) or None."""

        has_structural = structural is not None
        has_crossing = crossing is not None

        if not has_structural and not has_crossing:
            return None

        sb_ts = structural.confirmation_timestamp if structural else None
        ex_ts = crossing.timestamp if crossing else None
        sb_thr = float(structural.threshold_value) if structural else None
        ex_thr = float(crossing.threshold) if crossing else None
        sb_dir = structural.break_direction if structural else None
        ex_dir = self._crossing_direction(exchange_quotes) if crossing else None

        confirm_window = timedelta(minutes=DIVERGENCE_CONFIRM_WINDOW_MINUTES)
        align_window = timedelta(minutes=ALIGN_WINDOW_MINUTES)
        reversal_window = timedelta(minutes=REVERSAL_WINDOW_MINUTES)

        # Check reversal first
        if has_structural and has_crossing:
            leading_side = "EXCHANGE" if ex_ts < sb_ts else "SPORTSBOOK"  # type: ignore[operator]
            if leading_side == "EXCHANGE" and self._has_reversal_crossing(crossings, crossing, reversal_window):  # type: ignore[arg-type]
                return (DIVERGENCE_REVERTED, "EXCHANGE", sb_ts, ex_ts, sb_thr, ex_thr)
            if leading_side == "SPORTSBOOK" and structural and structural.reversal_detected:
                return (DIVERGENCE_REVERTED, "SPORTSBOOK", sb_ts, ex_ts, sb_thr, ex_thr)

        # OPPOSED / ALIGNED: both exist within alignment window
        if has_structural and has_crossing:
            delta = abs(sb_ts - ex_ts)  # type: ignore[operator]
            if delta <= align_window:
                if sb_dir and ex_dir and sb_dir != ex_dir:
                    return (DIVERGENCE_OPPOSED, "NONE", sb_ts, ex_ts, sb_thr, ex_thr)
                return (DIVERGENCE_ALIGNED, "NONE", sb_ts, ex_ts, sb_thr, ex_thr)

        # EXCHANGE_LEADS: exchange moved but sportsbook absent or late
        if has_crossing and (not has_structural or sb_ts > ex_ts + confirm_window):  # type: ignore[operator]
            return (DIVERGENCE_EXCHANGE_LEADS, "EXCHANGE", sb_ts, ex_ts, sb_thr, ex_thr)

        # SPORTSBOOK_LEADS: sportsbook moved but exchange absent or late
        if has_structural and (not has_crossing or ex_ts > sb_ts + confirm_window):  # type: ignore[operator]
            return (DIVERGENCE_SPORTSBOOK_LEADS, "SPORTSBOOK", sb_ts, ex_ts, sb_thr, ex_thr)

        # UNCONFIRMED: one side moved, other has quotes but no crossing
        if has_structural and not has_crossing and exchange_quotes:
            return (DIVERGENCE_UNCONFIRMED, "SPORTSBOOK", sb_ts, None, sb_thr, None)
        if has_crossing and not has_structural:
            return (DIVERGENCE_UNCONFIRMED, "EXCHANGE", None, ex_ts, None, ex_thr)

        return None

    @staticmethod
    def _crossing_direction(quotes: list[ExchangeQuoteEvent]) -> str | None:
        """Infer net direction from raw exchange quote probabilities (UP or DOWN)."""
        if len(quotes) < 2:
            return "UP"  # single quote treated as UP
        first_prob = quotes[0].probability
        last_prob = quotes[-1].probability
        if last_prob > first_prob:
            return "UP"
        if last_prob < first_prob:
            return "DOWN"
        return "UP"  # tie treated as UP

    @staticmethod
    def _has_reversal_crossing(
        crossings: list[ProbabilityCrossing],
        lead_crossing: ProbabilityCrossing,
        reversal_window: timedelta,
    ) -> bool:
        """Check if there's an opposite-direction crossing after lead within window."""
        cutoff = lead_crossing.timestamp + reversal_window
        after_lead = [c for c in crossings if c.timestamp > lead_crossing.timestamp and c.timestamp <= cutoff]
        if not after_lead:
            return False
        # If the latest post-lead crossing threshold is on the opposite side of the lead threshold
        return after_lead[-1].threshold < lead_crossing.threshold if lead_crossing.threshold > Decimal("0.5") else after_lead[-1].threshold > lead_crossing.threshold

    # ── resolution ───────────────────────────────────────────────────

    async def _resolve_prior_events(
        self,
        canonical_event_key: str,
        divergence_type: str,
        now: datetime,
    ) -> None:
        """Mark most recent unresolved lead-type events as resolved."""
        if divergence_type == DIVERGENCE_ALIGNED:
            resolution = "ALIGNED"
        elif divergence_type == DIVERGENCE_REVERTED:
            resolution = "REVERTED"
        else:
            return

        lead_types = {DIVERGENCE_EXCHANGE_LEADS, DIVERGENCE_SPORTSBOOK_LEADS}
        stmt = (
            update(CrossMarketDivergenceEvent)
            .where(
                CrossMarketDivergenceEvent.canonical_event_key == canonical_event_key,
                CrossMarketDivergenceEvent.divergence_type.in_(lead_types),
                CrossMarketDivergenceEvent.resolved.is_(False),
            )
            .values(resolved=True, resolved_at=now, resolution_type=resolution)
        )
        await self.db.execute(stmt)

    # ── data loading ─────────────────────────────────────────────────

    async def _load_alignment(self, canonical_event_key: str) -> CanonicalEventAlignment | None:
        stmt = select(CanonicalEventAlignment).where(
            CanonicalEventAlignment.canonical_event_key == canonical_event_key
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_latest_structural(
        self, sportsbook_event_id: str, freshness_cutoff: datetime
    ) -> StructuralEvent | None:
        stmt = (
            select(StructuralEvent)
            .where(
                StructuralEvent.event_id == sportsbook_event_id,
                StructuralEvent.confirmation_timestamp >= freshness_cutoff,
            )
            .order_by(StructuralEvent.confirmation_timestamp.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_exchange_quotes(
        self, canonical_event_key: str, freshness_cutoff: datetime
    ) -> list[ExchangeQuoteEvent]:
        stmt = (
            select(ExchangeQuoteEvent)
            .where(
                ExchangeQuoteEvent.canonical_event_key == canonical_event_key,
                ExchangeQuoteEvent.timestamp >= freshness_cutoff,
            )
            .order_by(ExchangeQuoteEvent.timestamp.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
