"""Deterministic structural threshold telemetry derived from quote move events."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN
from statistics import pstdev

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
from app.models.quote_move_event import QuoteMoveEvent
from app.models.structural_event import StructuralEvent
from app.models.structural_event_venue_participation import StructuralEventVenueParticipation

logger = logging.getLogger(__name__)

ADOPTION_WINDOW_MINUTES = 5
DISPERSION_WINDOW_MINUTES = 5
REVERSAL_WINDOW_MINUTES = 30
ACTIVE_SNAPSHOT_FRESHNESS_MINUTES = 3


@dataclass(frozen=True)
class StructuralCrossingCandidate:
    event_id: str
    market_key: str
    outcome_name: str
    threshold_value: Decimal
    direction: str
    venue: str
    venue_tier: str
    timestamp: datetime
    line_before: float | None
    line_after: float | None
    delta: float | None


@dataclass(frozen=True)
class StructuralEventCandidate:
    event_id: str
    market_key: str
    outcome_name: str
    threshold_value: Decimal
    threshold_type: str
    break_direction: str
    origin_venue: str
    origin_venue_tier: str
    origin_timestamp: datetime
    confirmation_timestamp: datetime
    candidates: tuple[StructuralCrossingCandidate, ...]


@dataclass(frozen=True)
class StructuralMetrics:
    adoption_percentage: float
    adoption_count: int
    active_venue_count: int
    time_to_consensus_seconds: int
    dispersion_pre: float | None
    dispersion_post: float | None
    break_hold_minutes: float
    reversal_detected: bool
    reversal_timestamp: datetime | None
    participating_venues: dict[str, StructuralCrossingCandidate]


class StructuralEventAnalysisService:
    """Deterministic structural threshold detector over quote move ledgers."""

    _THRESHOLD_STEP = Decimal("0.5")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_structural_events(self, game_id: str) -> list[StructuralEvent]:
        """Detect and persist structural threshold events for one game/event id."""
        if self.db.in_transaction():
            return await self._detect_structural_events_inner(game_id)
        async with self.db.begin():
            return await self._detect_structural_events_inner(game_id)

    async def _detect_structural_events_inner(self, game_id: str) -> list[StructuralEvent]:
        quote_moves = await self._load_quote_moves(game_id)
        if not quote_moves:
            return []

        groups = self._build_confirmed_groups(quote_moves)
        if not groups:
            return []

        persisted_ids: list[uuid.UUID] = []
        for group in groups:
            metrics = await self.compute_event_metrics(group, quote_moves)
            structural_event_id = await self._upsert_structural_event(group, metrics)
            await self._upsert_participation_rows(structural_event_id, group, metrics.participating_venues)
            persisted_ids.append(structural_event_id)
            logger.info(
                "STRUCTURAL_EVENT event_id=%s threshold=%.1f direction=%s origin=%s origin_tier=%s adoption=%.4f reversal=%s",
                group.event_id,
                float(group.threshold_value),
                group.break_direction,
                group.origin_venue,
                group.origin_venue_tier,
                metrics.adoption_percentage,
                metrics.reversal_detected,
            )

        if not persisted_ids:
            return []

        stmt = (
            select(StructuralEvent)
            .where(StructuralEvent.id.in_(persisted_ids))
            .order_by(StructuralEvent.confirmation_timestamp.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def compute_event_metrics(
        self,
        event: StructuralEventCandidate,
        quote_moves: list[QuoteMoveEvent],
    ) -> StructuralMetrics:
        """Compute deterministic telemetry metrics for a confirmed structural event."""
        origin = event.origin_timestamp
        adoption_end = origin + timedelta(minutes=ADOPTION_WINDOW_MINUTES)
        adoption_candidates = [
            candidate
            for candidate in event.candidates
            if origin <= candidate.timestamp <= adoption_end
        ]
        adoption_candidates.sort(key=lambda candidate: (candidate.timestamp, candidate.venue))

        participating_venues: dict[str, StructuralCrossingCandidate] = {}
        for candidate in adoption_candidates:
            if candidate.venue not in participating_venues:
                participating_venues[candidate.venue] = candidate

        adoption_count = len(participating_venues)
        active_venue_count = await self._compute_active_venue_count(event, origin)
        adoption_percentage = (
            float(adoption_count) / float(active_venue_count)
            if active_venue_count > 0
            else 0.0
        )

        time_to_consensus_seconds = int((event.confirmation_timestamp - origin).total_seconds())

        dispersion_pre = await self.compute_dispersion_window(
            event.event_id,
            event.market_key,
            event.outcome_name,
            origin - timedelta(minutes=DISPERSION_WINDOW_MINUTES),
            origin,
        )
        dispersion_post = await self.compute_dispersion_window(
            event.event_id,
            event.market_key,
            event.outcome_name,
            origin,
            origin + timedelta(minutes=DISPERSION_WINDOW_MINUTES),
        )

        reversal_detected, reversal_timestamp = self.detect_reversal(event, quote_moves)
        break_hold_minutes = self._compute_break_hold_minutes(event, quote_moves, reversal_timestamp)

        return StructuralMetrics(
            adoption_percentage=adoption_percentage,
            adoption_count=adoption_count,
            active_venue_count=active_venue_count,
            time_to_consensus_seconds=time_to_consensus_seconds,
            dispersion_pre=dispersion_pre,
            dispersion_post=dispersion_post,
            break_hold_minutes=break_hold_minutes,
            reversal_detected=reversal_detected,
            reversal_timestamp=reversal_timestamp,
            participating_venues=participating_venues,
        )

    def detect_reversal(
        self,
        event: StructuralEventCandidate,
        quote_moves: list[QuoteMoveEvent],
    ) -> tuple[bool, datetime | None]:
        """Detect whether an opposite structural break of the same threshold confirms."""
        reversal_window_end = event.confirmation_timestamp + timedelta(minutes=REVERSAL_WINDOW_MINUTES)
        opposite_direction = "DOWN" if event.break_direction == "UP" else "UP"

        reversal_candidates: list[StructuralCrossingCandidate] = []
        for move in quote_moves:
            if move.market_key != event.market_key or move.outcome_name != event.outcome_name:
                continue
            if move.timestamp <= event.confirmation_timestamp or move.timestamp > reversal_window_end:
                continue
            if move.old_line is None or move.new_line is None:
                continue
            direction = self._direction(move.old_line, move.new_line)
            if direction != opposite_direction:
                continue
            for threshold in self._crossed_thresholds(move.old_line, move.new_line):
                if threshold != event.threshold_value:
                    continue
                reversal_candidates.append(
                    StructuralCrossingCandidate(
                        event_id=move.event_id,
                        market_key=move.market_key,
                        outcome_name=move.outcome_name,
                        threshold_value=threshold,
                        direction=direction,
                        venue=move.venue,
                        venue_tier=move.venue_tier,
                        timestamp=move.timestamp,
                        line_before=move.old_line,
                        line_after=move.new_line,
                        delta=move.delta,
                    )
                )

        reversal_candidates.sort(key=lambda candidate: (candidate.timestamp, candidate.venue))
        confirmation_timestamp = self._find_confirmation_timestamp(reversal_candidates)
        if confirmation_timestamp is None:
            return False, None
        return True, confirmation_timestamp

    async def compute_dispersion_window(
        self,
        event_id: str,
        market_key: str,
        outcome_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> float | None:
        """Compute population standard deviation over latest per-venue lines in a window."""
        latest_lines = await self._latest_snapshot_lines_by_venue(
            event_id=event_id,
            market_key=market_key,
            outcome_name=outcome_name,
            start_time=start_time,
            end_time=end_time,
        )
        values = list(latest_lines.values())
        if len(values) < 2:
            return None
        return float(pstdev(values))

    async def _load_quote_moves(self, game_id: str) -> list[QuoteMoveEvent]:
        stmt = (
            select(QuoteMoveEvent)
            .where(
                QuoteMoveEvent.event_id == game_id,
                QuoteMoveEvent.market_key == "spreads",
                QuoteMoveEvent.old_line.isnot(None),
                QuoteMoveEvent.new_line.isnot(None),
            )
            .order_by(QuoteMoveEvent.timestamp.asc(), QuoteMoveEvent.venue.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    def _build_confirmed_groups(
        self,
        quote_moves: list[QuoteMoveEvent],
    ) -> list[StructuralEventCandidate]:
        grouped: dict[
            tuple[str, str, str, Decimal, str],
            list[StructuralCrossingCandidate],
        ] = defaultdict(list)

        for move in quote_moves:
            if move.old_line is None or move.new_line is None:
                continue
            direction = self._direction(move.old_line, move.new_line)
            if direction is None:
                continue
            for threshold in self._crossed_thresholds(move.old_line, move.new_line):
                key = (
                    move.event_id,
                    move.market_key,
                    move.outcome_name,
                    threshold,
                    direction,
                )
                grouped[key].append(
                    StructuralCrossingCandidate(
                        event_id=move.event_id,
                        market_key=move.market_key,
                        outcome_name=move.outcome_name,
                        threshold_value=threshold,
                        direction=direction,
                        venue=move.venue,
                        venue_tier=move.venue_tier,
                        timestamp=move.timestamp,
                        line_before=move.old_line,
                        line_after=move.new_line,
                        delta=move.delta,
                    )
                )

        events: list[StructuralEventCandidate] = []
        for (
            event_id,
            market_key,
            outcome_name,
            threshold_value,
            direction,
        ), candidates in grouped.items():
            ordered_candidates = sorted(
                candidates,
                key=lambda candidate: (candidate.timestamp, candidate.venue),
            )
            confirmation_timestamp = self._find_confirmation_timestamp(ordered_candidates)
            if confirmation_timestamp is None:
                continue
            origin = ordered_candidates[0]
            events.append(
                StructuralEventCandidate(
                    event_id=event_id,
                    market_key=market_key,
                    outcome_name=outcome_name,
                    threshold_value=threshold_value,
                    threshold_type=self._threshold_type(threshold_value),
                    break_direction=direction,
                    origin_venue=origin.venue,
                    origin_venue_tier=origin.venue_tier,
                    origin_timestamp=origin.timestamp,
                    confirmation_timestamp=confirmation_timestamp,
                    candidates=tuple(ordered_candidates),
                )
            )

        events.sort(
            key=lambda event: (
                event.confirmation_timestamp,
                event.event_id,
                event.market_key,
                event.outcome_name,
                float(event.threshold_value),
                event.break_direction,
            )
        )
        return events

    async def _compute_active_venue_count(
        self,
        event: StructuralEventCandidate,
        origin_timestamp: datetime,
    ) -> int:
        window_start = origin_timestamp - timedelta(minutes=ADOPTION_WINDOW_MINUTES)
        freshness_cutoff = origin_timestamp - timedelta(minutes=ACTIVE_SNAPSHOT_FRESHNESS_MINUTES)
        lower_bound = max(window_start, freshness_cutoff)
        upper_bound = origin_timestamp + timedelta(minutes=ADOPTION_WINDOW_MINUTES)

        latest_lines = await self._latest_snapshot_lines_by_venue(
            event_id=event.event_id,
            market_key=event.market_key,
            outcome_name=event.outcome_name,
            start_time=lower_bound,
            end_time=upper_bound,
        )
        return len(latest_lines)

    async def _latest_snapshot_lines_by_venue(
        self,
        *,
        event_id: str,
        market_key: str,
        outcome_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, float]:
        if end_time < start_time:
            return {}

        stmt = (
            select(
                OddsSnapshot.sportsbook_key,
                OddsSnapshot.line,
                OddsSnapshot.fetched_at,
            )
            .where(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.market == market_key,
                OddsSnapshot.outcome_name == outcome_name,
                OddsSnapshot.fetched_at >= start_time,
                OddsSnapshot.fetched_at <= end_time,
                OddsSnapshot.line.isnot(None),
            )
            .order_by(OddsSnapshot.sportsbook_key.asc(), OddsSnapshot.fetched_at.desc())
        )
        rows = (await self.db.execute(stmt)).all()
        latest_lines: dict[str, float] = {}
        for sportsbook_key, line, _fetched_at in rows:
            if sportsbook_key in latest_lines or line is None:
                continue
            latest_lines[sportsbook_key] = float(line)
        return latest_lines

    async def _upsert_structural_event(
        self,
        event: StructuralEventCandidate,
        metrics: StructuralMetrics,
    ) -> uuid.UUID:
        now = datetime.now(UTC)
        values = {
            "event_id": event.event_id,
            "market_key": event.market_key,
            "outcome_name": event.outcome_name,
            "threshold_value": float(event.threshold_value),
            "threshold_type": event.threshold_type,
            "break_direction": event.break_direction,
            "origin_venue": event.origin_venue,
            "origin_venue_tier": event.origin_venue_tier,
            "origin_timestamp": event.origin_timestamp,
            "confirmation_timestamp": event.confirmation_timestamp,
            "adoption_percentage": metrics.adoption_percentage,
            "adoption_count": metrics.adoption_count,
            "active_venue_count": metrics.active_venue_count,
            "time_to_consensus_seconds": metrics.time_to_consensus_seconds,
            "dispersion_pre": metrics.dispersion_pre,
            "dispersion_post": metrics.dispersion_post,
            "break_hold_minutes": metrics.break_hold_minutes,
            "reversal_detected": metrics.reversal_detected,
            "reversal_timestamp": metrics.reversal_timestamp,
            "created_at": now,
            "updated_at": now,
        }
        stmt = pg_insert(StructuralEvent).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                StructuralEvent.event_id,
                StructuralEvent.market_key,
                StructuralEvent.outcome_name,
                StructuralEvent.threshold_value,
                StructuralEvent.break_direction,
            ],
            set_={
                "threshold_type": stmt.excluded.threshold_type,
                "origin_venue": stmt.excluded.origin_venue,
                "origin_venue_tier": stmt.excluded.origin_venue_tier,
                "origin_timestamp": stmt.excluded.origin_timestamp,
                "confirmation_timestamp": stmt.excluded.confirmation_timestamp,
                "adoption_percentage": stmt.excluded.adoption_percentage,
                "adoption_count": stmt.excluded.adoption_count,
                "active_venue_count": stmt.excluded.active_venue_count,
                "time_to_consensus_seconds": stmt.excluded.time_to_consensus_seconds,
                "dispersion_pre": stmt.excluded.dispersion_pre,
                "dispersion_post": stmt.excluded.dispersion_post,
                "break_hold_minutes": stmt.excluded.break_hold_minutes,
                "reversal_detected": stmt.excluded.reversal_detected,
                "reversal_timestamp": stmt.excluded.reversal_timestamp,
                "updated_at": now,
            },
        ).returning(StructuralEvent.id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _upsert_participation_rows(
        self,
        structural_event_id: uuid.UUID,
        event: StructuralEventCandidate,
        participating_venues: dict[str, StructuralCrossingCandidate],
    ) -> None:
        if not participating_venues:
            return

        rows = []
        for venue in sorted(participating_venues):
            candidate = participating_venues[venue]
            rows.append(
                {
                    "structural_event_id": structural_event_id,
                    "event_id": event.event_id,
                    "market_key": event.market_key,
                    "outcome_name": event.outcome_name,
                    "venue": candidate.venue,
                    "venue_tier": candidate.venue_tier,
                    "crossed_at": candidate.timestamp,
                    "line_before": candidate.line_before,
                    "line_after": candidate.line_after,
                    "delta": candidate.delta,
                }
            )
        stmt = pg_insert(StructuralEventVenueParticipation).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[
                StructuralEventVenueParticipation.structural_event_id,
                StructuralEventVenueParticipation.venue,
            ]
        )
        await self.db.execute(stmt)

    def _compute_break_hold_minutes(
        self,
        event: StructuralEventCandidate,
        quote_moves: list[QuoteMoveEvent],
        reversal_timestamp: datetime | None,
    ) -> float:
        window_end = event.confirmation_timestamp + timedelta(minutes=REVERSAL_WINDOW_MINUTES)
        if reversal_timestamp is not None:
            hold_end = reversal_timestamp
        else:
            relevant_timestamps = [
                move.timestamp
                for move in quote_moves
                if move.market_key == event.market_key
                and move.outcome_name == event.outcome_name
                and event.confirmation_timestamp < move.timestamp <= window_end
            ]
            last_observed = max(relevant_timestamps) if relevant_timestamps else None
            hold_end = min(last_observed, window_end) if last_observed is not None else window_end
        return max(0.0, (hold_end - event.confirmation_timestamp).total_seconds() / 60.0)

    def _find_confirmation_timestamp(
        self,
        candidates: list[StructuralCrossingCandidate],
    ) -> datetime | None:
        venues: set[str] = set()
        t1_seen = False
        for candidate in sorted(candidates, key=lambda row: (row.timestamp, row.venue)):
            venues.add(candidate.venue)
            if candidate.venue_tier.upper() == "T1":
                t1_seen = True
            if len(venues) >= 2 or t1_seen:
                return candidate.timestamp
        return None

    def _crossed_thresholds(self, old_line: float, new_line: float) -> list[Decimal]:
        old_dec = Decimal(str(old_line))
        new_dec = Decimal(str(new_line))
        if old_dec == new_dec:
            return []

        old_units = old_dec / self._THRESHOLD_STEP
        new_units = new_dec / self._THRESHOLD_STEP
        if new_dec > old_dec:
            start = int(old_units.to_integral_value(rounding=ROUND_FLOOR)) + 1
            end = int(new_units.to_integral_value(rounding=ROUND_FLOOR))
            if end < start:
                return []
            return [
                self._normalize_threshold_value(Decimal(step) * self._THRESHOLD_STEP)
                for step in range(start, end + 1)
            ]

        start = int(old_units.to_integral_value(rounding=ROUND_CEILING)) - 1
        end = int(new_units.to_integral_value(rounding=ROUND_CEILING))
        if start < end:
            return []
        return [
            self._normalize_threshold_value(Decimal(step) * self._THRESHOLD_STEP)
            for step in range(start, end - 1, -1)
        ]

    def _normalize_threshold_value(self, value: Decimal) -> Decimal:
        half_steps = (value / self._THRESHOLD_STEP).to_integral_value(rounding=ROUND_HALF_EVEN)
        return half_steps * self._THRESHOLD_STEP

    def _threshold_type(self, threshold_value: Decimal) -> str:
        fraction = abs(threshold_value % Decimal("1"))
        return "INTEGER" if fraction == Decimal("0") else "HALF"

    def _direction(self, old_line: float, new_line: float) -> str | None:
        if new_line > old_line:
            return "UP"
        if new_line < old_line:
            return "DOWN"
        return None
