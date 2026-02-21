from fastapi import APIRouter, Request
from sqlalchemy import text

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
