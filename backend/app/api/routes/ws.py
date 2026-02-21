import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User
from sqlalchemy import select

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

async def get_current_user_ws(token: str) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    try:
        parsed_user_id = UUID(user_id)
    except ValueError:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == parsed_user_id))
        return result.scalar_one_or_none()

@router.websocket("/odds")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    # 1. Authenticate and authorize (Pro/Admin only)
    user = await get_current_user_ws(token)
    if not user:
        logger.warning("WebSocket: User not found for token")
        await websocket.close(code=1008)
        return

    if user.tier != "pro" and not user.is_admin:
        logger.warning(f"WebSocket: User {user.email} is not authorized (Tier: {user.tier}, Admin: {user.is_admin})")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info(f"WebSocket ACCEPTED for user {user.email}")
    
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("odds_updates")
    
    logger.info(f"WebSocket connected for user {user.email}")

    try:
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if not message:
                continue
            if message.get("type") != "message":
                continue

            data = message["data"]
            await websocket.send_text(data)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user.email}")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        await pubsub.unsubscribe("odds_updates")
        await pubsub.aclose()
        await redis.aclose()
