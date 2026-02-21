import asyncio
import logging
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

# Track polling cycles to run periodic cleanup
cycle_count = 0


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


async def run_polling_cycle(redis: Redis | None) -> None:
    async with AsyncSessionLocal() as db:
        ingest_result = await ingest_odds_cycle(db, redis)
        event_ids = ingest_result.get("event_ids", [])
        if not event_ids:
            logger.info("No updated events this cycle")
            return

        signals = await detect_market_movements(db, redis, event_ids)
        await dispatch_discord_alerts_for_signals(db, signals)


async def main() -> None:
    global cycle_count
    setup_logging()
    logger.info("Starting odds poller", extra={"interval_seconds": settings.odds_poll_interval_seconds})

    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
    except Exception:
        logger.exception("Redis unavailable, poller running without lock/dedupe cache")
        redis = None

    while True:
        cycle_start = time.monotonic()
        try:
            async with redis_cycle_lock(redis, "poller:odds-ingest-lock") as acquired:
                if acquired:
                    await run_polling_cycle(redis)
                    
                    # Run cleanup every ~60 cycles (approx 1 hour at 60s intervals)
                    cycle_count += 1
                    if cycle_count >= 60:
                        cycle_count = 0
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

        elapsed = time.monotonic() - cycle_start
        sleep_seconds = max(1, settings.odds_poll_interval_seconds - elapsed)
        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    asyncio.run(main())
