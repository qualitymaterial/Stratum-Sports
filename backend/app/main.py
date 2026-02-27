import logging
from typing import Optional
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.api.router import api_router
from app.core.api_usage_middleware import ApiUsageTrackingMiddleware
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limit import RedisRateLimitMiddleware

settings = get_settings()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(
        "Database URL configuration active",
        extra={
            "database_url_source": settings.resolved_database_url_source,
            "database_host": (
                settings.postgres_host if settings.resolved_database_url_source == "postgres_fallback" else None
            ),
            "database_port": (
                settings.postgres_port if settings.resolved_database_url_source == "postgres_fallback" else None
            ),
            "database_name": (
                settings.postgres_db if settings.resolved_database_url_source == "postgres_fallback" else None
            ),
        },
    )
    redis: Optional[Redis] = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        app.state.redis = redis
        logger.info("Redis connected")
    except Exception:
        app.state.redis = None
        logger.exception("Redis connection failed")

    yield

    if redis is not None:
        await redis.aclose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
)
app.add_middleware(RedisRateLimitMiddleware, requests_per_minute=180)
app.add_middleware(ApiUsageTrackingMiddleware)

app.include_router(api_router, prefix="/api/v1")
