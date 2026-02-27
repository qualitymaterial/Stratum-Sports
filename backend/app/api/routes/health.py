from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

router = APIRouter()


@router.get("/health/live")
async def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request) -> dict:
    redis_ok = False
    db_ok = False

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            pong = await redis.ping()
            redis_ok = bool(pong)
        except Exception:
            redis_ok = False

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    status = "ok" if db_ok and redis_ok else "degraded"
    return {"status": status, "db": db_ok, "redis": redis_ok}


@router.get("/health/flags")
async def health_flags() -> dict:
    s = get_settings()
    return {
        "staging_validation_mode": s.staging_validation_mode,
        "consensus_enabled": s.consensus_enabled,
        "dislocation_enabled": s.dislocation_enabled,
        "steam_enabled": s.steam_enabled,
        "clv_enabled": s.clv_enabled,
        "regime_detection_enabled": s.effective_regime_detection_enabled,
        "enable_historical_backfill": s.enable_historical_backfill,
        "exchange_divergence_signal_enabled": s.exchange_divergence_signal_enabled,
        "time_bucket_expose_inplay": s.time_bucket_expose_inplay,
        "free_delay_minutes": s.free_delay_minutes,
        "api_usage_tracking_enabled": s.api_usage_tracking_enabled,
    }
