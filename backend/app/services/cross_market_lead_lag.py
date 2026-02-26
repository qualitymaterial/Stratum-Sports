"""Deterministic cross-market lead–lag computation between sportsbook and exchange events."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_lead_lag_event import CrossMarketLeadLagEvent
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.structural_event import StructuralEvent

logger = logging.getLogger(__name__)

# ── constants (single source of truth) ──────────────────────────────
PROB_STEP = Decimal("0.025")
ALIGN_WINDOW_MINUTES = 10


# ── data classes ────────────────────────────────────────────────────
@dataclass(frozen=True, order=True)
class ProbabilityCrossing:
    """One detected probability threshold crossing."""

    timestamp: datetime
    market_id: str
    source: str
    threshold: Decimal  # the boundary value crossed


# ── service ─────────────────────────────────────────────────────────
class CrossMarketLeadLagService:
    """Aligns sportsbook structural events with exchange probability crossings.

    Algorithm (fully deterministic):
    1. Look up the sportsbook_event_id from the CanonicalEventAlignment row.
    2. Fetch StructuralEvent rows for that sportsbook_event_id.
    3. Fetch ExchangeQuoteEvent rows for the canonical_event_key.
    4. Detect probability threshold crossings (0.025-step).
    5. For each StructuralEvent, find the nearest exchange crossing within ±10 min.
    6. Persist a CrossMarketLeadLagEvent (ON CONFLICT DO NOTHING).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compute_lead_lag(self, canonical_event_key: str) -> int:
        """Run the full lead-lag pipeline. Returns number of rows inserted."""

        # 1. Resolve sportsbook event id
        alignment = await self._load_alignment(canonical_event_key)
        if alignment is None:
            return 0

        # 2. Fetch sportsbook structural events
        structural_events = await self._load_structural_events(alignment.sportsbook_event_id)
        if not structural_events:
            return 0

        # 3. Fetch exchange quotes
        exchange_quotes = await self._load_exchange_quotes(canonical_event_key)
        if not exchange_quotes:
            return 0

        # 4. Detect probability crossings
        crossings = detect_probability_crossings(exchange_quotes)
        if not crossings:
            return 0

        # 5. Align and persist
        inserted = 0
        for se in structural_events:
            best = self._find_nearest_crossing(se, crossings)
            if best is None:
                continue

            sportsbook_ts = se.confirmation_timestamp
            exchange_ts = best.timestamp

            lead_source = "EXCHANGE" if exchange_ts < sportsbook_ts else "SPORTSBOOK"
            lag_seconds = int(abs((exchange_ts - sportsbook_ts).total_seconds()))

            values = {
                "canonical_event_key": canonical_event_key,
                "threshold_type": "SPREAD_THRESHOLD",
                "sportsbook_threshold_value": float(se.threshold_value),
                "exchange_probability_threshold": float(best.threshold),
                "lead_source": lead_source,
                "sportsbook_break_timestamp": sportsbook_ts,
                "exchange_break_timestamp": exchange_ts,
                "lag_seconds": lag_seconds,
            }
            stmt = pg_insert(CrossMarketLeadLagEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_cross_market_lead_lag_identity",
            )
            result = await self.db.execute(stmt)
            if result.rowcount > 0:
                inserted += 1

        await self.db.flush()

        logger.info(
            "Cross-market lead-lag computed",
            extra={
                "canonical_event_key": canonical_event_key,
                "structural_events": len(structural_events),
                "exchange_crossings": len(crossings),
                "lead_lag_inserted": inserted,
            },
        )
        return inserted

    # ── private helpers ──────────────────────────────────────────────

    async def _load_alignment(self, canonical_event_key: str) -> CanonicalEventAlignment | None:
        stmt = select(CanonicalEventAlignment).where(
            CanonicalEventAlignment.canonical_event_key == canonical_event_key
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_structural_events(self, sportsbook_event_id: str) -> list[StructuralEvent]:
        stmt = (
            select(StructuralEvent)
            .where(StructuralEvent.event_id == sportsbook_event_id)
            .order_by(StructuralEvent.confirmation_timestamp.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _load_exchange_quotes(self, canonical_event_key: str) -> list[ExchangeQuoteEvent]:
        stmt = (
            select(ExchangeQuoteEvent)
            .where(ExchangeQuoteEvent.canonical_event_key == canonical_event_key)
            .order_by(ExchangeQuoteEvent.timestamp.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _find_nearest_crossing(
        se: StructuralEvent,
        crossings: list[ProbabilityCrossing],
    ) -> ProbabilityCrossing | None:
        """Find the exchange crossing closest to the sportsbook break timestamp.

        Only crossings within ±ALIGN_WINDOW_MINUTES are considered.
        Tie-break: smaller absolute time delta, then earlier exchange timestamp.
        """
        window = timedelta(minutes=ALIGN_WINDOW_MINUTES)
        sportsbook_ts = se.confirmation_timestamp
        best: ProbabilityCrossing | None = None
        best_delta: timedelta | None = None

        for crossing in crossings:
            delta = abs(crossing.timestamp - sportsbook_ts)
            if delta > window:
                continue
            if best_delta is None or delta < best_delta or (
                delta == best_delta and crossing.timestamp < best.timestamp  # type: ignore[union-attr]
            ):
                best = crossing
                best_delta = delta

        return best


# ── probability threshold detection (pure function) ─────────────────
def detect_probability_crossings(
    quotes: list[ExchangeQuoteEvent],
) -> list[ProbabilityCrossing]:
    """Detect 0.025-step probability threshold crossings.

    Walks the quote list in chronological order per (source, market_id)
    group.  For each consecutive pair of probability values, emits one
    ProbabilityCrossing per boundary crossed.

    Uses Decimal arithmetic throughout to avoid floating-point drift.
    """
    # Group by (source, market_id) — deterministic ordering
    groups: dict[tuple[str, str], list[ExchangeQuoteEvent]] = {}
    for q in quotes:
        key = (q.source, q.market_id)
        groups.setdefault(key, []).append(q)

    crossings: list[ProbabilityCrossing] = []

    for (source, market_id), group_quotes in sorted(groups.items()):
        sorted_quotes = sorted(group_quotes, key=lambda q: q.timestamp)
        prev: ExchangeQuoteEvent | None = None
        for quote in sorted_quotes:
            if prev is not None:
                thresholds = _crossed_thresholds(
                    float(prev.probability), float(quote.probability)
                )
                for threshold in thresholds:
                    crossings.append(
                        ProbabilityCrossing(
                            timestamp=quote.timestamp,
                            market_id=market_id,
                            source=source,
                            threshold=threshold,
                        )
                    )
            prev = quote

    # Deterministic ordering: time asc, market_id, source, threshold
    crossings.sort(key=lambda c: (c.timestamp, c.market_id, c.source, c.threshold))
    return crossings


def _crossed_thresholds(old_prob: float, new_prob: float) -> list[Decimal]:
    """Return every 0.025 boundary crossed between two probability values.

    Uses Decimal-safe math.  Returns thresholds in the direction of
    movement (ascending if upward, descending if downward).
    """
    old_dec = Decimal(str(old_prob))
    new_dec = Decimal(str(new_prob))
    if old_dec == new_dec:
        return []

    old_units = old_dec / PROB_STEP
    new_units = new_dec / PROB_STEP

    if new_dec > old_dec:
        # Upward: first boundary strictly above old, up to boundary at/below new
        start = int(old_units.to_integral_value(rounding=ROUND_FLOOR)) + 1
        end = int(new_units.to_integral_value(rounding=ROUND_FLOOR))
        if end < start:
            return []
        return [Decimal(step) * PROB_STEP for step in range(start, end + 1)]

    # Downward: first boundary strictly below old, down to boundary at/above new
    start = int(old_units.to_integral_value(rounding=ROUND_CEILING)) - 1
    end = int(new_units.to_integral_value(rounding=ROUND_CEILING))
    if start < end:
        return []
    return [Decimal(step) * PROB_STEP for step in range(start, end - 1, -1)]
