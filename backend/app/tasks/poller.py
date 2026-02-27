import asyncio
import logging
import math
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import setup_logging
from app.models.game import Game
from app.services.closing import cleanup_old_closing_consensus
from app.services.clv import cleanup_old_clv_records, compute_and_persist_clv
from app.services.consensus import cleanup_old_consensus_snapshots
from app.services.discord_alerts import dispatch_discord_alerts_for_signals
from app.services.historical_backfill import backfill_missing_closing_consensus
from app.services.ingestion import cleanup_old_signals, cleanup_old_snapshots, ingest_odds_cycle
from app.services.kpis import build_cycle_kpi, cleanup_old_cycle_kpis, persist_cycle_kpi
from app.services.ops_digest import maybe_send_weekly_ops_digest
from app.services.propagation import detect_propagation_events
from app.services.signals import detect_market_movements, summarize_signals_by_type
from app.adapters.exchange.errors import ExchangeUpstreamError
from app.adapters.exchange.kalshi_client import KalshiClient
from app.adapters.exchange.polymarket_client import PolymarketClient
from app.services.cross_market_divergence import CrossMarketDivergenceService
from app.services.cross_market_lead_lag import CrossMarketLeadLagService
from app.services.exchange_ingestion import ExchangeIngestionService
from app.services.structural_events import StructuralEventAnalysisService

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class CloseCaptureState:
    next_poll_at_by_event: dict[str, datetime] = field(default_factory=dict)
    cadence_seconds_by_event: dict[str, int] = field(default_factory=dict)
    stop_logged_events: set[str] = field(default_factory=set)
    next_discovery_at: datetime | None = None


def _close_capture_cadence_seconds(minutes_to_tip: float) -> int | None:
    default_far_seconds = max(15 * 60, settings.odds_poll_interval_seconds)
    if minutes_to_tip > 180:
        return default_far_seconds
    if minutes_to_tip > 60:
        return 5 * 60
    if minutes_to_tip > -15:
        return 60
    return None


async def _build_close_capture_plan(db, state: CloseCaptureState, now_utc: datetime) -> dict:
    sport_keys = settings.odds_api_sport_keys_list
    multi_sport_mode = len(sport_keys) > 1
    window_start = now_utc - timedelta(minutes=30)
    window_end = now_utc + timedelta(hours=6)
    stmt = (
        select(Game.event_id, Game.commence_time)
        .where(
            Game.sport_key.in_(sport_keys),
            Game.commence_time >= window_start,
            Game.commence_time <= window_end,
        )
        .order_by(Game.commence_time.asc(), Game.event_id.asc())
    )
    rows = (await db.execute(stmt)).all()

    candidate_ids: set[str] = set()
    due_events: list[tuple[datetime, str, int]] = []

    for event_id, commence_time in rows:
        candidate_ids.add(event_id)
        minutes_to_tip = (commence_time - now_utc).total_seconds() / 60.0
        cadence_seconds = _close_capture_cadence_seconds(minutes_to_tip)
        previous_cadence = state.cadence_seconds_by_event.get(event_id)

        if cadence_seconds is None:
            if event_id not in state.stop_logged_events:
                logger.info(
                    "[CLOSE-CAPTURE] event=%s minutes_to_tip=%.2f stop=true",
                    event_id,
                    minutes_to_tip,
                )
                state.stop_logged_events.add(event_id)
            state.next_poll_at_by_event.pop(event_id, None)
            state.cadence_seconds_by_event.pop(event_id, None)
            continue

        state.stop_logged_events.discard(event_id)
        state.cadence_seconds_by_event[event_id] = cadence_seconds

        if previous_cadence is None or cadence_seconds < previous_cadence:
            logger.info(
                "[CLOSE-CAPTURE] event=%s minutes_to_tip=%.2f cadence=%ss",
                event_id,
                minutes_to_tip,
                cadence_seconds,
            )
            state.next_poll_at_by_event[event_id] = now_utc

        if event_id not in state.next_poll_at_by_event:
            state.next_poll_at_by_event[event_id] = now_utc

        if now_utc >= state.next_poll_at_by_event[event_id]:
            due_events.append((commence_time, event_id, cadence_seconds))

    stale_event_ids = [event_id for event_id in state.next_poll_at_by_event if event_id not in candidate_ids]
    for event_id in stale_event_ids:
        state.next_poll_at_by_event.pop(event_id, None)
        state.cadence_seconds_by_event.pop(event_id, None)
        state.stop_logged_events.discard(event_id)

    due_events.sort(key=lambda row: (row[0], row[1]))
    max_events = max(1, settings.stratum_close_capture_max_events_per_cycle)
    selected_due_events = due_events[:max_events]
    overflow_due_events = due_events[max_events:]
    selected_event_ids = [event_id for _commence_time, event_id, _cadence in selected_due_events]

    for _commence_time, event_id, cadence_seconds in selected_due_events:
        state.next_poll_at_by_event[event_id] = now_utc + timedelta(seconds=cadence_seconds)
    for _commence_time, event_id, cadence_seconds in overflow_due_events:
        state.next_poll_at_by_event[event_id] = now_utc + timedelta(seconds=cadence_seconds)

    if rows:
        state.next_discovery_at = None

    should_discovery_poll = False
    if not selected_event_ids and not rows:
        discovery_interval = max(60, settings.odds_poll_interval_idle_seconds)
        if state.next_discovery_at is None or now_utc >= state.next_discovery_at:
            should_discovery_poll = True
            state.next_discovery_at = now_utc + timedelta(seconds=discovery_interval)

    next_due_seconds: int | None = None
    scheduled_times = list(state.next_poll_at_by_event.values())
    if state.next_discovery_at is not None:
        scheduled_times.append(state.next_discovery_at)
    if scheduled_times:
        next_due_seconds = max(1, int(math.ceil((min(scheduled_times) - now_utc).total_seconds())))

    return {
        "events_considered": len(rows),
        "events_due_total": len(due_events),
        "events_due_selected": len(selected_event_ids),
        "eligible_event_ids": None if multi_sport_mode else (selected_event_ids if selected_event_ids else None),
        "skip_ingest": False if multi_sport_mode else (not should_discovery_poll and len(selected_event_ids) == 0),
        "next_due_seconds": next_due_seconds,
        "multi_sport_mode": multi_sport_mode,
    }


def determine_poll_interval(cycle_result: dict | None) -> int:
    def _apply_manual_override(calculated_interval: int) -> int:
        forced = os.getenv("POLL_INTERVAL_SECONDS")
        if forced:
            try:
                forced_int = max(5, int(forced))
                logger.info("Manual polling override applied", extra={"forced_seconds": forced_int})
                return forced_int
            except ValueError:
                pass
        return calculated_interval

    active_interval = max(1, settings.odds_poll_interval_seconds)
    idle_interval = max(1, settings.odds_poll_interval_idle_seconds)
    low_credit_interval = max(1, settings.odds_poll_interval_low_credit_seconds)

    if not cycle_result:
        return _apply_manual_override(active_interval)

    next_due_seconds = cycle_result.get("close_capture_next_due_seconds")
    close_capture_due_interval: int | None = None
    if isinstance(next_due_seconds, int) and next_due_seconds > 0:
        close_capture_due_interval = max(1, next_due_seconds)

    remaining = cycle_result.get("api_requests_remaining")
    if isinstance(remaining, int) and remaining <= settings.odds_api_low_credit_threshold:
        if close_capture_due_interval is not None:
            return _apply_manual_override(max(low_credit_interval, close_capture_due_interval))
        return _apply_manual_override(low_credit_interval)

    events_seen = cycle_result.get("events_seen", 0)
    if isinstance(events_seen, int) and events_seen == 0:
        target_interval = idle_interval
    else:
        target_interval = active_interval

    requests_last = cycle_result.get("api_requests_last")
    if isinstance(requests_last, int) and requests_last > 0 and settings.odds_api_target_daily_credits > 0:
        budget_interval = math.ceil((requests_last * 86400) / settings.odds_api_target_daily_credits)
        target_interval = max(target_interval, max(1, budget_interval))

    if close_capture_due_interval is not None:
        if isinstance(events_seen, int) and events_seen == 0:
            target_interval = close_capture_due_interval
        else:
            target_interval = max(target_interval, close_capture_due_interval)

    return _apply_manual_override(target_interval)


@asynccontextmanager
async def redis_cycle_lock(redis: Redis | None, lock_key: str, ttl_seconds: int = 55):
    if redis is None:
        yield True
        return

    lock_value = str(uuid.uuid4())
    try:
        acquired = await redis.set(lock_key, lock_value, ex=ttl_seconds, nx=True)
    except Exception:
        logger.exception("Failed to acquire redis lock")
        yield True
        return

    if not acquired:
        yield False
        return

    try:
        yield True
    finally:
        try:
            current = await redis.get(lock_key)
            if current == lock_value:
                await redis.delete(lock_key)
        except Exception:
            logger.exception("Failed to release redis lock")


async def run_polling_cycle(
    redis: Redis | None,
    close_capture_state: CloseCaptureState | None = None,
) -> dict:
    async with AsyncSessionLocal() as db:
        close_capture_plan = {
            "events_considered": 0,
            "events_due_total": 0,
            "events_due_selected": 0,
            "eligible_event_ids": None,
            "skip_ingest": False,
            "next_due_seconds": None,
        }
        if settings.stratum_close_capture_enabled and close_capture_state is not None:
            close_capture_plan = await _build_close_capture_plan(db, close_capture_state, datetime.now(UTC))

        if close_capture_plan["skip_ingest"]:
            logger.info(
                "Skipping ingest; no close-capture events due",
                extra={
                    "events_considered": close_capture_plan["events_considered"],
                    "events_due_total": close_capture_plan["events_due_total"],
                    "next_due_seconds": close_capture_plan["next_due_seconds"],
                },
            )
            return {
                "inserted": 0,
                "events_seen": 0,
                "events_processed": 0,
                "snapshots_inserted": 0,
                "event_ids": [],
                "event_ids_updated": [],
                "consensus_points_written": 0,
                "consensus_failed": False,
                "signals_created": 0,
                "signals_created_total": 0,
                "signals_created_by_type": {},
                "alerts_sent": 0,
                "alerts_failed": 0,
                "structural_events_created": 0,
                "cross_market_events_created": 0,
                "cross_market_divergence_events_created": 0,
                "kalshi_markets_polled": 0,
                "kalshi_quotes_inserted": 0,
                "kalshi_errors": 0,
                "kalshi_skipped_no_alignment": 0,
                "kalshi_skipped_no_market_id": 0,
                "polymarket_markets_polled": 0,
                "polymarket_quotes_inserted": 0,
                "close_capture_events_considered": close_capture_plan["events_considered"],
                "close_capture_events_due_total": close_capture_plan["events_due_total"],
                "close_capture_events_due_selected": close_capture_plan["events_due_selected"],
                "close_capture_next_due_seconds": close_capture_plan["next_due_seconds"],
            }

        eligible_event_ids = close_capture_plan.get("eligible_event_ids")
        ingest_result = await ingest_odds_cycle(
            db,
            redis,
            eligible_event_ids=set(eligible_event_ids) if eligible_event_ids is not None else None,
        )
        ingest_result["close_capture_events_considered"] = close_capture_plan["events_considered"]
        ingest_result["close_capture_events_due_total"] = close_capture_plan["events_due_total"]
        ingest_result["close_capture_events_due_selected"] = close_capture_plan["events_due_selected"]
        ingest_result["close_capture_next_due_seconds"] = close_capture_plan["next_due_seconds"]
        event_ids = ingest_result.get("event_ids_updated") or ingest_result.get("event_ids", [])
        if not event_ids:
            logger.info("No updated events this cycle")
            ingest_result["signals_created"] = 0
            ingest_result["signals_created_total"] = 0
            ingest_result["signals_created_by_type"] = {}
            ingest_result["alerts_sent"] = 0
            ingest_result["alerts_failed"] = 0
            ingest_result["structural_events_created"] = 0
            ingest_result["cross_market_events_created"] = 0
            ingest_result["cross_market_divergence_events_created"] = 0
            ingest_result["kalshi_markets_polled"] = 0
            ingest_result["kalshi_quotes_inserted"] = 0
            ingest_result["kalshi_errors"] = 0
            ingest_result["kalshi_skipped_no_alignment"] = 0
            ingest_result["kalshi_skipped_no_market_id"] = 0
            ingest_result["polymarket_markets_polled"] = 0
            ingest_result["polymarket_quotes_inserted"] = 0
            return ingest_result

        signals = await detect_market_movements(db, redis, event_ids)
        signal_counts = summarize_signals_by_type(signals)

        # --- Propagation detection (additive, does not affect signals) ---
        propagation_count = 0
        try:
            prop_events = await detect_propagation_events(db, event_ids)
            propagation_count = len(prop_events)
            if prop_events:
                await db.commit()
        except Exception:
            logger.exception("Propagation detection failed; continuing")

        structural_count = 0
        structural_service = StructuralEventAnalysisService(db)
        for event_id in event_ids:
            try:
                structural_events = await structural_service.detect_structural_events(event_id)
                structural_count += len(structural_events)
            except Exception:
                logger.exception(
                    "Structural event detection failed; continuing",
                    extra={"event_id": event_id},
                )

        # --- Exchange adapter ingestion (Kalshi live, Polymarket disabled by default) ---
        kalshi_markets_polled = 0
        kalshi_quotes_inserted = 0
        kalshi_errors = 0
        kalshi_skipped_no_alignment = 0
        kalshi_skipped_no_market_id = 0
        polymarket_markets_polled = 0
        polymarket_quotes_inserted = 0
        kalshi_alignments_synced = 0
        alignment_objs: list = []
        alignment_ceks: list[str] = []
        try:
            from app.models.canonical_event_alignment import CanonicalEventAlignment
            from app.services.alignment_service import EventAlignmentService

            # Auto-align upcoming sportsbook games with Kalshi markets
            alignment_service = EventAlignmentService(db, KalshiClient())
            try:
                kalshi_alignments_synced = await alignment_service.sync_kalshi_alignments()
            except Exception:
                logger.exception("Kalshi alignment sync failed; continuing with existing alignments")

            exchange_ingestion = ExchangeIngestionService(db)

            # Load alignment rows once for both exchange blocks and cross-market hooks
            alignment_stmt = select(CanonicalEventAlignment).where(
                CanonicalEventAlignment.sportsbook_event_id.in_(event_ids)
            )
            alignment_objs = list((await db.execute(alignment_stmt)).scalars().all())

            aligned_event_ids = {a.sportsbook_event_id for a in alignment_objs}
            kalshi_skipped_no_alignment = len(set(event_ids) - aligned_event_ids)

            # --- Kalshi ingestion ---
            kalshi_skipped_no_market_id = len([a for a in alignment_objs if not a.kalshi_market_id])
            kalshi_alignments = [a for a in alignment_objs if a.kalshi_market_id]
            max_kalshi = settings.max_kalshi_markets_per_cycle
            if max_kalshi is not None:
                kalshi_alignments = kalshi_alignments[:max_kalshi]
            if kalshi_alignments:
                try:
                    kalshi_client = KalshiClient()
                    for alignment in kalshi_alignments:
                        try:
                            raw = await kalshi_client.fetch_market_quotes(alignment.kalshi_market_id)  # type: ignore[arg-type]
                            inserted = await exchange_ingestion.ingest_exchange_quotes(
                                canonical_event_key=alignment.canonical_event_key,
                                source="KALSHI",
                                raw_payload=raw,
                            )
                            kalshi_quotes_inserted += inserted
                            kalshi_markets_polled += 1
                        except ExchangeUpstreamError:
                            kalshi_errors += 1
                            logger.exception(
                                "Kalshi fetch failed; continuing",
                                extra={"kalshi_market_id": alignment.kalshi_market_id},
                            )
                        except Exception:
                            kalshi_errors += 1
                            logger.exception(
                                "Kalshi ingestion failed; continuing",
                                extra={"kalshi_market_id": alignment.kalshi_market_id},
                            )
                    if kalshi_quotes_inserted > 0:
                        await db.commit()
                except Exception:
                    logger.exception("Kalshi ingestion pipeline failed; continuing")

            # --- Polymarket ingestion (disabled by default) ---
            if settings.enable_polymarket_ingest:
                poly_alignments = [
                    a for a in alignment_objs if a.polymarket_market_id
                ][:settings.max_polymarket_markets_per_cycle]
                if poly_alignments:
                    try:
                        poly_client = PolymarketClient()
                        for alignment in poly_alignments:
                            try:
                                raw = await poly_client.fetch_market_quotes(alignment.polymarket_market_id)  # type: ignore[arg-type]
                                inserted = await exchange_ingestion.ingest_exchange_quotes(
                                    canonical_event_key=alignment.canonical_event_key,
                                    source="POLYMARKET",
                                    raw_payload=raw,
                                )
                                polymarket_quotes_inserted += inserted
                                polymarket_markets_polled += 1
                            except ExchangeUpstreamError:
                                logger.exception(
                                    "Polymarket fetch failed; continuing",
                                    extra={"polymarket_market_id": alignment.polymarket_market_id},
                                )
                            except Exception:
                                logger.exception(
                                    "Polymarket ingestion failed; continuing",
                                    extra={"polymarket_market_id": alignment.polymarket_market_id},
                                )
                        if polymarket_quotes_inserted > 0:
                            await db.commit()
                    except Exception:
                        logger.exception("Polymarket ingestion pipeline failed; continuing")
        except Exception:
            logger.exception("Exchange adapter pipeline failed; continuing")

        # --- Cross-market lead-lag (additive) ---
        cross_market_count = 0
        alignment_ceks = [a.canonical_event_key for a in alignment_objs] if alignment_objs else []
        try:
            lead_lag_service = CrossMarketLeadLagService(db)
            for cek in alignment_ceks:
                try:
                    cross_market_count += await lead_lag_service.compute_lead_lag(cek)
                except Exception:
                    logger.exception(
                        "Cross-market lead-lag failed; continuing",
                        extra={"canonical_event_key": cek},
                    )
            if cross_market_count > 0:
                await db.commit()
        except Exception:
            logger.exception("Cross-market lead-lag pipeline failed; continuing")

        # --- Cross-market divergence (additive) ---
        divergence_count = 0
        try:
            divergence_service = CrossMarketDivergenceService(db)
            for cek in alignment_ceks:
                try:
                    divergence_count += await divergence_service.compute_divergence(cek)
                except Exception:
                    logger.exception(
                        "Cross-market divergence failed; continuing",
                        extra={"canonical_event_key": cek},
                    )
            if divergence_count > 0:
                await db.commit()
        except Exception:
            logger.exception("Cross-market divergence pipeline failed; continuing")

        # --- EXCHANGE_DIVERGENCE signal generation (reads divergence events just computed) ---
        if alignment_ceks and settings.exchange_divergence_signal_enabled:
            try:
                from app.services.signals import detect_exchange_divergence_signals

                exchange_div_event_ids = [a.sportsbook_event_id for a in alignment_objs]
                exchange_divergence_signals = await detect_exchange_divergence_signals(
                    exchange_div_event_ids, db, redis
                )
                if exchange_divergence_signals:
                    await db.commit()
                    signals.extend(exchange_divergence_signals)
            except Exception:
                logger.exception("Exchange divergence signal generation failed; continuing")

        # --- Regime detection (metadata-only enrichment, feature-flagged) ---
        regime_enriched = 0
        if settings.effective_regime_detection_enabled and signals:
            try:
                from app.regime.config import regime_config_from_settings
                from app.regime.service import RegimeService

                regime_config = regime_config_from_settings(settings)
                regime_svc = RegimeService(db, regime_config)
                regime_event_ids = list({s.event_id for s in signals})
                enriched, _persisted = await regime_svc.run(regime_event_ids, signals)
                regime_enriched = enriched
            except Exception:
                logger.exception("Regime detection failed; continuing")

        alert_stats = await dispatch_discord_alerts_for_signals(db, signals, redis=redis)
        ingest_result["signals_created"] = len(signals)
        ingest_result["signals_created_total"] = len(signals)
        ingest_result["signals_created_by_type"] = signal_counts
        ingest_result["alerts_sent"] = int(alert_stats.get("sent", 0))
        ingest_result["alerts_failed"] = int(alert_stats.get("failed", 0))
        ingest_result["propagation_events_created"] = propagation_count
        ingest_result["structural_events_created"] = structural_count
        ingest_result["kalshi_alignments_synced"] = kalshi_alignments_synced
        ingest_result["cross_market_events_created"] = cross_market_count
        ingest_result["cross_market_divergence_events_created"] = divergence_count
        ingest_result["kalshi_markets_polled"] = kalshi_markets_polled
        ingest_result["kalshi_quotes_inserted"] = kalshi_quotes_inserted
        ingest_result["kalshi_errors"] = kalshi_errors
        ingest_result["kalshi_skipped_no_alignment"] = kalshi_skipped_no_alignment
        ingest_result["kalshi_skipped_no_market_id"] = kalshi_skipped_no_market_id
        ingest_result["polymarket_markets_polled"] = polymarket_markets_polled
        ingest_result["polymarket_quotes_inserted"] = polymarket_quotes_inserted
        ingest_result["regime_signals_enriched"] = regime_enriched

        logger.info(
            "KALSHI_INGEST_SUMMARY polled=%d inserted=%d errors=%d skipped_no_alignment=%d skipped_no_market=%d",
            kalshi_markets_polled,
            kalshi_quotes_inserted,
            kalshi_errors,
            kalshi_skipped_no_alignment,
            kalshi_skipped_no_market_id,
        )

        return ingest_result


async def main() -> None:
    setup_logging()
    logger.info(
        "Starting odds poller",
        extra={
            "active_interval_seconds": settings.odds_poll_interval_seconds,
            "idle_interval_seconds": settings.odds_poll_interval_idle_seconds,
            "low_credit_interval_seconds": settings.odds_poll_interval_low_credit_seconds,
            "low_credit_threshold": settings.odds_api_low_credit_threshold,
            "target_daily_credits": settings.odds_api_target_daily_credits,
            "close_capture_enabled": settings.stratum_close_capture_enabled,
            "close_capture_max_events_per_cycle": settings.stratum_close_capture_max_events_per_cycle,
            "odds_api_sport_keys": settings.odds_api_sport_keys_list,
        },
    )

    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
    except Exception:
        logger.exception("Redis unavailable, poller running without lock/dedupe cache")
        redis = None

    last_cleanup_monotonic = 0.0
    last_clv_monotonic = 0.0
    last_historical_backfill_monotonic = 0.0
    last_api_usage_flush_monotonic = 0.0
    close_capture_state = CloseCaptureState()

    while True:
        cycle_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        cycle_start = time.monotonic()
        cycle_result: dict | None = None
        cycle_error: str | None = None
        cycle_notes: dict[str, object] = {}
        cycle_degraded = False
        acquired_lock = False
        try:
            async with redis_cycle_lock(redis, "poller:odds-ingest-lock") as acquired:
                if acquired:
                    acquired_lock = True
                    cycle_result = await run_polling_cycle(redis, close_capture_state=close_capture_state)
                    now_monotonic = time.monotonic()

                    if settings.ops_digest_enabled:
                        try:
                            async with AsyncSessionLocal() as db:
                                digest_result = await maybe_send_weekly_ops_digest(
                                    db,
                                    redis,
                                    now_utc=datetime.now(UTC),
                                )
                                if digest_result.get("sent"):
                                    logger.info(
                                        "Ops weekly digest sent",
                                        extra={
                                            "week_key": digest_result.get("week_key"),
                                            "status_code": digest_result.get("status_code"),
                                        },
                                    )
                        except Exception:
                            logger.exception("Ops digest job failed")

                    if settings.enable_historical_backfill:
                        history_job_interval_seconds = max(1, settings.historical_backfill_interval_minutes) * 60
                        if (now_monotonic - last_historical_backfill_monotonic) >= history_job_interval_seconds:
                            last_historical_backfill_monotonic = now_monotonic
                            try:
                                backfill_metrics = await backfill_missing_closing_consensus(
                                    lookback_hours=settings.historical_backfill_lookback_hours,
                                    max_games=settings.historical_backfill_max_games_per_run,
                                    settings=settings,
                                )
                                logger.info("Historical backfill job completed", extra=backfill_metrics)
                            except Exception:
                                logger.exception("Historical backfill job failed")

                            if settings.clv_enabled:
                                last_clv_monotonic = now_monotonic
                                try:
                                    async with AsyncSessionLocal() as db:
                                        clv_inserted = await compute_and_persist_clv(
                                            db,
                                            days_lookback=settings.clv_lookback_days,
                                        )
                                        if clv_inserted > 0:
                                            logger.info("CLV job completed", extra={"clv_records_inserted": clv_inserted})
                                except Exception:
                                    logger.exception("CLV job failed")
                    else:
                        clv_interval_seconds = max(1, settings.clv_job_interval_minutes) * 60
                        if settings.clv_enabled and (now_monotonic - last_clv_monotonic) >= clv_interval_seconds:
                            last_clv_monotonic = now_monotonic
                            try:
                                async with AsyncSessionLocal() as db:
                                    clv_inserted = await compute_and_persist_clv(
                                        db,
                                        days_lookback=settings.clv_lookback_days,
                                    )
                                    if clv_inserted > 0:
                                        logger.info("CLV job completed", extra={"clv_records_inserted": clv_inserted})
                            except Exception:
                                logger.exception("CLV job failed")

                    if now_monotonic - last_cleanup_monotonic >= 3600:
                        last_cleanup_monotonic = now_monotonic
                        async with AsyncSessionLocal() as db:
                            deleted_snaps = await cleanup_old_snapshots(db)
                            deleted_signals = await cleanup_old_signals(db)
                            deleted_consensus = await cleanup_old_consensus_snapshots(db)
                            deleted_closing = await cleanup_old_closing_consensus(db)
                            deleted_clv = await cleanup_old_clv_records(db)
                            deleted_kpis = await cleanup_old_cycle_kpis(db, settings.kpi_retention_days)
                            if (
                                deleted_snaps > 0
                                or deleted_signals > 0
                                or deleted_consensus > 0
                                or deleted_closing > 0
                                or deleted_clv > 0
                                or deleted_kpis > 0
                            ):
                                logger.info(
                                    "Retention cleanup completed",
                                    extra={
                                        "snapshots_deleted": deleted_snaps,
                                        "signals_deleted": deleted_signals,
                                        "consensus_snapshots_deleted": deleted_consensus,
                                        "closing_consensus_deleted": deleted_closing,
                                        "clv_records_deleted": deleted_clv,
                                        "cycle_kpis_deleted": deleted_kpis,
                                    },
                                )
                    # --- API usage flush (periodic) ---
                    api_usage_flush_interval = max(60, settings.api_usage_flush_interval_seconds)
                    if settings.api_usage_tracking_enabled and (now_monotonic - last_api_usage_flush_monotonic) >= api_usage_flush_interval:
                        last_api_usage_flush_monotonic = now_monotonic
                        try:
                            from app.services.stripe_meter_publisher import flush_and_sync_all
                            flush_result = await flush_and_sync_all(redis)
                            if flush_result.get("flushed", 0) > 0 or flush_result.get("metered", 0) > 0:
                                logger.info("API usage flush completed", extra=flush_result)
                        except Exception:
                            logger.exception("API usage flush job failed")

                else:
                    acquired_lock = False
                    cycle_notes["lock_held"] = True
                    logger.info("Skipping cycle because lock is held")
        except Exception as exc:
            cycle_error = str(exc)
            logger.exception("Polling cycle failed")

        target_interval = determine_poll_interval(cycle_result)
        elapsed = time.monotonic() - cycle_start
        sleep_seconds = max(1, target_interval - elapsed)

        if redis is None:
            cycle_degraded = True
            cycle_notes["redis_unavailable"] = True
        if cycle_error:
            cycle_degraded = True
        if cycle_result and cycle_result.get("consensus_failed"):
            cycle_degraded = True
            cycle_notes["consensus_failed"] = True
        remaining = (cycle_result or {}).get("api_requests_remaining")
        if isinstance(remaining, int) and remaining <= settings.odds_api_low_credit_threshold:
            cycle_degraded = True
            cycle_notes["low_credit"] = True

        completed_at = datetime.now(UTC)
        duration_ms = max(0, int((time.monotonic() - cycle_start) * 1000))

        # Credit burn rate logging for staging validation
        if cycle_result:
            _burn_remaining = cycle_result.get("api_requests_remaining")
            _burn_last = cycle_result.get("api_requests_last", 0)
            if isinstance(_burn_remaining, int) and isinstance(_burn_last, int) and _burn_last > 0:
                _daily_burn = (_burn_last * 86400) / max(1, target_interval)
                _daily_budget = max(1, settings.odds_api_target_daily_credits)
                logger.info(
                    "Credit burn check",
                    extra={
                        "remaining_credits": _burn_remaining,
                        "credits_used_this_cycle": _burn_last,
                        "projected_daily_burn": round(_daily_burn),
                        "daily_budget": _daily_budget,
                        "budget_pct": round(_daily_burn / _daily_budget * 100, 1),
                        "staging_validation_mode": settings.staging_validation_mode,
                    },
                )

        if settings.kpi_enabled:
            kpi_context = {
                "cycle_id": cycle_id,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "requests_used_delta": (cycle_result or {}).get("api_requests_last"),
                "requests_remaining": (cycle_result or {}).get("api_requests_remaining"),
                "requests_limit": (cycle_result or {}).get("api_requests_limit"),
                "events_processed": (cycle_result or {}).get("events_processed", (cycle_result or {}).get("events_seen")),
                "snapshots_inserted": (cycle_result or {}).get(
                    "snapshots_inserted",
                    (cycle_result or {}).get("inserted"),
                ),
                "consensus_points_written": (cycle_result or {}).get("consensus_points_written"),
                "signals_created_total": (cycle_result or {}).get(
                    "signals_created_total",
                    (cycle_result or {}).get("signals_created"),
                ),
                "signals_created_by_type": (cycle_result or {}).get("signals_created_by_type"),
                "alerts_sent": (cycle_result or {}).get("alerts_sent"),
                "alerts_failed": (cycle_result or {}).get("alerts_failed"),
                "error": cycle_error,
                "degraded": cycle_degraded,
                "notes": {
                    **cycle_notes,
                    "target_interval_seconds": target_interval,
                    "acquired_lock": acquired_lock,
                },
            }
            try:
                async with AsyncSessionLocal() as db:
                    await persist_cycle_kpi(db, build_cycle_kpi(kpi_context))
            except Exception:
                logger.exception("Cycle KPI persistence orchestration failed")

        if target_interval != settings.odds_poll_interval_seconds:
            logger.info(
                "Adaptive polling interval applied",
                extra={
                    "target_interval_seconds": target_interval,
                    "sleep_seconds": round(sleep_seconds, 2),
                    "events_seen": (cycle_result or {}).get("events_seen"),
                    "api_requests_remaining": (cycle_result or {}).get("api_requests_remaining"),
                    "api_requests_last": (cycle_result or {}).get("api_requests_last"),
                },
            )

        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    asyncio.run(main())
