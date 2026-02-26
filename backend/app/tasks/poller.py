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
from app.services.signals import detect_market_movements, summarize_signals_by_type

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
            return ingest_result

        signals = await detect_market_movements(db, redis, event_ids)
        signal_counts = summarize_signals_by_type(signals)
        alert_stats = await dispatch_discord_alerts_for_signals(db, signals, redis=redis)
        ingest_result["signals_created"] = len(signals)
        ingest_result["signals_created_total"] = len(signals)
        ingest_result["signals_created_by_type"] = signal_counts
        ingest_result["alerts_sent"] = int(alert_stats.get("sent", 0))
        ingest_result["alerts_failed"] = int(alert_stats.get("failed", 0))
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
