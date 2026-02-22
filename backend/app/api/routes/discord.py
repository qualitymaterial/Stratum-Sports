from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_pro_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.discord_connection import DiscordConnection
from app.models.user import User
from app.schemas.discord import DiscordConnectionUpsert

router = APIRouter()
settings = get_settings()


def _is_valid_discord_webhook_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if host not in set(settings.discord_webhook_allowed_hosts_list):
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 4:
        return False
    return path_parts[0] == "api" and path_parts[1] == "webhooks"


@router.get("/connection")
async def get_connection(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_pro_user),
) -> dict:
    stmt = select(DiscordConnection).where(DiscordConnection.user_id == user.id)
    connection = (await db.execute(stmt)).scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discord connection not found")

    return {
        "id": connection.id,
        "webhook_url": connection.webhook_url,
        "is_enabled": connection.is_enabled,
        "alert_spreads": connection.alert_spreads,
        "alert_totals": connection.alert_totals,
        "alert_multibook": connection.alert_multibook,
        "min_strength": connection.min_strength,
        "thresholds": connection.thresholds_json,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


@router.put("/connection")
async def upsert_connection(
    payload: DiscordConnectionUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_pro_user),
) -> dict:
    if not _is_valid_discord_webhook_url(payload.webhook_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook URL must be a Discord webhook endpoint (https://discord.com/api/webhooks/...).",
        )

    stmt = select(DiscordConnection).where(DiscordConnection.user_id == user.id)
    connection = (await db.execute(stmt)).scalar_one_or_none()

    if connection is None:
        connection = DiscordConnection(
            user_id=user.id,
            webhook_url=payload.webhook_url,
            is_enabled=payload.is_enabled,
            alert_spreads=payload.alert_spreads,
            alert_totals=payload.alert_totals,
            alert_multibook=payload.alert_multibook,
            min_strength=payload.min_strength,
            thresholds_json=payload.thresholds.model_dump(),
        )
        db.add(connection)
    else:
        connection.webhook_url = payload.webhook_url
        connection.is_enabled = payload.is_enabled
        connection.alert_spreads = payload.alert_spreads
        connection.alert_totals = payload.alert_totals
        connection.alert_multibook = payload.alert_multibook
        connection.min_strength = payload.min_strength
        connection.thresholds_json = payload.thresholds.model_dump()

    await db.commit()
    await db.refresh(connection)

    return {
        "id": connection.id,
        "webhook_url": connection.webhook_url,
        "is_enabled": connection.is_enabled,
        "alert_spreads": connection.alert_spreads,
        "alert_totals": connection.alert_totals,
        "alert_multibook": connection.alert_multibook,
        "min_strength": connection.min_strength,
        "thresholds": connection.thresholds_json,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }
