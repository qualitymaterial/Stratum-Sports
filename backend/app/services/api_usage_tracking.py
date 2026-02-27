"""API usage tracking: Redis hot-path counters + periodic DB flush."""

import calendar
import logging
from datetime import UTC, date, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.api_partner_usage_period import ApiPartnerUsagePeriod

logger = logging.getLogger(__name__)


def _redis_user_key(user_id: str, month: str) -> str:
    prefix = get_settings().api_usage_redis_key_prefix
    return f"{prefix}:{user_id}:{month}"


def _redis_key_key(user_id: str, key_id: str, month: str) -> str:
    prefix = get_settings().api_usage_redis_key_prefix
    return f"{prefix}:{user_id}:key:{key_id}:{month}"


def _current_month_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _period_bounds(month_str: str) -> tuple[date, date]:
    """Return (period_start, period_end) for a YYYY-MM string."""
    year, month = int(month_str[:4]), int(month_str[5:7])
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return first, last


async def increment_usage(redis: Redis, user_id: str, key_id: str | None) -> int:
    """Increment user-level (and optionally key-level) counters. Returns new user count."""
    month = _current_month_str()
    user_key = _redis_user_key(user_id, month)

    pipe = redis.pipeline(transaction=False)
    pipe.incr(user_key)
    pipe.expire(user_key, 40 * 86400)  # 40-day TTL

    if key_id:
        kk = _redis_key_key(user_id, key_id, month)
        pipe.incr(kk)
        pipe.expire(kk, 40 * 86400)

    results = await pipe.execute()
    return int(results[0])


async def get_current_usage(redis: Redis, user_id: str) -> int:
    """Read current month counter for a user."""
    month = _current_month_str()
    val = await redis.get(_redis_user_key(user_id, month))
    return int(val) if val else 0


async def get_cached_soft_limit(redis: Redis, user_id: str) -> int | None:
    """Read cached soft_limit (24h cache to avoid DB hit per request)."""
    prefix = get_settings().api_usage_redis_key_prefix
    val = await redis.get(f"{prefix}:limit:{user_id}")
    if val is None:
        return None
    return int(val)


async def cache_soft_limit(redis: Redis, user_id: str, limit: int | None) -> None:
    """Cache soft_limit for 24 hours. Stores -1 for 'no limit'."""
    prefix = get_settings().api_usage_redis_key_prefix
    cache_key = f"{prefix}:limit:{user_id}"
    await redis.set(cache_key, str(limit if limit is not None else -1), ex=86400)


async def get_usage_and_limits(
    redis: Redis,
    db: AsyncSession,
    user_id: str,
) -> dict:
    """Return current usage, limits, and overage info for a user."""
    month = _current_month_str()
    period_start, period_end = _period_bounds(month)
    request_count = await get_current_usage(redis, user_id)

    # Try cached limit first
    cached = await get_cached_soft_limit(redis, user_id)
    if cached is None:
        stmt = select(ApiPartnerEntitlement).where(
            ApiPartnerEntitlement.user_id == user_id
        )
        ent = (await db.execute(stmt)).scalar_one_or_none()
        soft_limit = ent.soft_limit_monthly if ent else None
        overage_enabled = ent.overage_enabled if ent else False
        await cache_soft_limit(redis, user_id, soft_limit)
    else:
        soft_limit = None if cached == -1 else cached
        # For overage_enabled we need DB — only matters for detailed view
        overage_enabled = False

    remaining = max(0, soft_limit - request_count) if soft_limit is not None else None
    is_over_limit = (soft_limit is not None) and (request_count > soft_limit)
    overage_count = max(0, request_count - soft_limit) if is_over_limit else 0

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "request_count": request_count,
        "included_limit": soft_limit,
        "remaining": remaining,
        "is_over_limit": is_over_limit,
        "overage_count": overage_count,
        "overage_enabled": overage_enabled,
    }


async def flush_usage_to_db(
    db: AsyncSession,
    redis: Redis,
    user_id: str,
    key_id: str | None = None,
) -> ApiPartnerUsagePeriod | None:
    """Read Redis counters and upsert into api_partner_usage_periods."""
    month = _current_month_str()
    period_start, period_end = _period_bounds(month)

    user_key = _redis_user_key(user_id, month)
    count_raw = await redis.get(user_key)
    request_count = int(count_raw) if count_raw else 0
    if request_count == 0:
        return None

    # Fetch soft limit for included_limit snapshot
    stmt = select(ApiPartnerEntitlement).where(
        ApiPartnerEntitlement.user_id == user_id
    )
    ent = (await db.execute(stmt)).scalar_one_or_none()
    included_limit = ent.soft_limit_monthly if ent else None
    overage = max(0, request_count - included_limit) if included_limit is not None else 0

    insert_stmt = pg_insert(ApiPartnerUsagePeriod).values(
        user_id=user_id,
        key_id=key_id,
        period_start=period_start,
        period_end=period_end,
        request_count=request_count,
        included_limit=included_limit,
        overage_count=overage,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_usage_period_user_key_start",
        set_={
            "request_count": request_count,
            "included_limit": included_limit,
            "overage_count": overage,
            "period_end": period_end,
            "updated_at": datetime.now(UTC),
        },
    )
    await db.execute(upsert_stmt)
    await db.commit()

    # Fetch the upserted row
    fetch_stmt = select(ApiPartnerUsagePeriod).where(
        ApiPartnerUsagePeriod.user_id == user_id,
        ApiPartnerUsagePeriod.period_start == period_start,
    )
    if key_id:
        fetch_stmt = fetch_stmt.where(ApiPartnerUsagePeriod.key_id == key_id)
    else:
        fetch_stmt = fetch_stmt.where(ApiPartnerUsagePeriod.key_id.is_(None))

    return (await db.execute(fetch_stmt)).scalar_one_or_none()


async def get_usage_history(
    db: AsyncSession,
    user_id: str,
    limit: int = 12,
    offset: int = 0,
) -> list[ApiPartnerUsagePeriod]:
    """Historical usage periods ordered by period_start DESC."""
    stmt = (
        select(ApiPartnerUsagePeriod)
        .where(ApiPartnerUsagePeriod.user_id == user_id)
        .order_by(ApiPartnerUsagePeriod.period_start.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())
