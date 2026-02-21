import asyncio
import logging
import math
import time
import uuid
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import setup_logging
from app.services.discord_alerts import dispatch_discord_alerts_for_signals
from app.services.ingestion import cleanup_old_signals, cleanup_old_snapshots, ingest_odds_cycle
from app.services.signals import detect_market_movements

settings = get_settings()
logger = logging.getLogger(__name__)

def determine_poll_interval(cycle_result: dict | None) -> int:
    active_interval = max(1, settings.odds_poll_interval_seconds)
    idle_interval = max(1, settings.odds_poll_interval_idle_seconds)
    low_credit_interval = max(1, settings.odds_poll_interval_low_credit_seconds)

    if not cycle_result:
        return active_interval

    remaining = cycle_result.get("api_requests_remaining")
    if isinstance(remaining, int) and remaining <= settings.odds_api_low_credit_threshold:
        return low_credit_interval

    events_seen = cycle_result.get("events_seen", 0)
    if isinstance(events_seen, int) and events_seen == 0:
        target_interval = idle_interval
    else:
        target_interval = active_interval

    requests_last = cycle_result.get("api_requests_last")
    if isinstance(requests_last, int) and requests_last > 0 and settings.odds_api_target_daily_credits > 0:
        budget_interval = math.ceil((requests_last * 86400) / settings.odds_api_target_daily_credits)
        target_interval = max(target_interval, max(1, budget_interval))

    return target_interval


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


async def run_polling_cycle(redis: Redis | None) -> dict:
    async with AsyncSessionLocal() as db:
        ingest_result = await ingest_odds_cycle(db, redis)
        event_ids = ingest_result.get("event_ids", [])
        if not event_ids:
            logger.info("No updated events this cycle")
            return ingest_result

        signals = await detect_market_movements(db, redis, event_ids)
        alerts_sent = await dispatch_discord_alerts_for_signals(db, signals)
        ingest_result["signals_created"] = len(signals)
        ingest_result["alerts_sent"] = alerts_sent
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

    while True:
        cycle_start = time.monotonic()
        cycle_result: dict | None = None
        try:
            async with redis_cycle_lock(redis, "poller:odds-ingest-lock") as acquired:
                if acquired:
                    cycle_result = await run_polling_cycle(redis)
                    now_monotonic = time.monotonic()
                    if now_monotonic - last_cleanup_monotonic >= 3600:
                        last_cleanup_monotonic = now_monotonic
                        async with AsyncSessionLocal() as db:
                            deleted_snaps = await cleanup_old_snapshots(db)
                            deleted_signals = await cleanup_old_signals(db)
                            if deleted_snaps > 0 or deleted_signals > 0:
                                logger.info(
                                    "Retention cleanup completed",
                                    extra={
                                        "snapshots_deleted": deleted_snaps,
                                        "signals_deleted": deleted_signals,
                                    },
                                )
                else:
                    logger.info("Skipping cycle because lock is held")
        except Exception:
            logger.exception("Polling cycle failed")

        target_interval = determine_poll_interval(cycle_result)
        elapsed = time.monotonic() - cycle_start
        sleep_seconds = max(1, target_interval - elapsed)

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
