import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User

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


async def receive_ws_auth_token(websocket: WebSocket) -> str | None:
    try:
        raw_message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
    except TimeoutError:
        return None
    except WebSocketDisconnect:
        return None
    except Exception:
        logger.exception("WebSocket auth receive failed")
        return None

    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "auth":
        return None

    token = payload.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    return token


@router.websocket("/odds")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    token = await receive_ws_auth_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return

    user = await get_current_user_ws(token)
    if not user:
        await websocket.close(code=1008)
        return

    if user.tier != "pro" and not user.is_admin:
        await websocket.close(code=1008)
        return

    await websocket.send_json({"type": "auth_ok"})
    logger.info("WebSocket authenticated", extra={"user_id": str(user.id), "tier": user.tier})

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("odds_updates")

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
        logger.info("WebSocket disconnected", extra={"user_id": str(user.id)})
    except Exception:
        logger.exception("WebSocket error")
    finally:
        await pubsub.unsubscribe("odds_updates")
        await pubsub.aclose()
        await redis.aclose()
