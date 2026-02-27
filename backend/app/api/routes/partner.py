"""Partner self-serve endpoints for API usage visibility and billing."""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, HttpUrl

from app.api.deps import get_current_user, get_current_user_or_api_partner
from app.core.database import get_db
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.api_partner_webhook import ApiPartnerWebhook, WebhookDeliveryLog
from app.models.user import User

router = APIRouter()


class WebhookCreate(BaseModel):
    url: HttpUrl
    description: str | None = None


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    description: str | None = None
    is_active: bool | None = None


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    description: str | None = None
    is_active: bool
    secret: str

    class Config:
        from_attributes = True


class WebhookLogOut(BaseModel):
    id: uuid.UUID
    webhook_id: uuid.UUID
    signal_id: uuid.UUID | None
    status_code: int | None
    duration_ms: int
    error: str | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/webhooks", response_model=list[WebhookOut])
async def list_partner_webhooks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> list:
    """List all webhooks for the authenticated partner."""
    stmt = select(ApiPartnerWebhook).where(ApiPartnerWebhook.user_id == user.id)
    webhooks = (await db.execute(stmt)).scalars().all()
    return [
        WebhookOut.model_validate(w)
        for w in webhooks
    ]


@router.post("/webhooks", response_model=WebhookOut)
async def create_partner_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> WebhookOut:
    """Create a new webhook for the partner."""
    import secrets
    
    # Check limit? (e.g. max 5 webhooks)
    stmt = select(ApiPartnerWebhook).where(ApiPartnerWebhook.user_id == user.id)
    count = len((await db.execute(stmt)).scalars().all())
    if count >= 5:
        raise HTTPException(status_code=400, detail="Maximum of 5 webhooks allowed")

    webhook = ApiPartnerWebhook(
        user_id=user.id,
        url=str(payload.url),
        description=payload.description,
        secret=f"whsec_{secrets.token_hex(24)}"
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return WebhookOut.model_validate(webhook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_partner_webhook(
    webhook_id: uuid.UUID,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> WebhookOut:
    """Update a partner webhook."""
    stmt = select(ApiPartnerWebhook).where(
        ApiPartnerWebhook.id == webhook_id, ApiPartnerWebhook.user_id == user.id
    )
    webhook = (await db.execute(stmt)).scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if payload.url is not None:
        webhook.url = str(payload.url)
    if payload.description is not None:
        webhook.description = payload.description
    if payload.is_active is not None:
        webhook.is_active = payload.is_active

    await db.commit()
    await db.refresh(webhook)
    return WebhookOut(
        id=webhook.id,
        url=webhook.url,
        description=webhook.description,
        is_active=webhook.is_active,
        secret=webhook.secret,
    )


@router.post("/webhooks/{webhook_id}/secret", response_model=WebhookOut)
async def rotate_partner_webhook_secret(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> WebhookOut:
    """Rotate the signing secret for a webhook."""
    import secrets
    stmt = select(ApiPartnerWebhook).where(
        ApiPartnerWebhook.id == webhook_id, ApiPartnerWebhook.user_id == user.id
    )
    webhook = (await db.execute(stmt)).scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    webhook.secret = f"whsec_{secrets.token_hex(24)}"
    await db.commit()
    await db.refresh(webhook)
    return WebhookOut(
        id=webhook.id,
        url=webhook.url,
        description=webhook.description,
        is_active=webhook.is_active,
        secret=webhook.secret,
    )


@router.delete("/webhooks/{webhook_id}")
async def delete_partner_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> dict:
    """Delete a partner webhook."""
    stmt = select(ApiPartnerWebhook).where(
        ApiPartnerWebhook.id == webhook_id, ApiPartnerWebhook.user_id == user.id
    )
    webhook = (await db.execute(stmt)).scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db.delete(webhook)
    await db.commit()
    return {"status": "deleted"}


@router.get("/webhooks/logs", response_model=list[WebhookLogOut])
async def list_partner_webhook_logs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
    webhook_id: uuid.UUID | None = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list:
    """List delivery logs for the partner's webhooks."""
    stmt = (
        select(WebhookDeliveryLog)
        .join(ApiPartnerWebhook)
        .where(ApiPartnerWebhook.user_id == user.id)
    )
    
    if webhook_id:
        stmt = stmt.where(WebhookDeliveryLog.webhook_id == webhook_id)
        
    stmt = stmt.order_by(desc(WebhookDeliveryLog.created_at)).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    
    return [
        WebhookLogOut.model_validate(l)
        for l in logs
    ]


@router.get("/usage")
async def get_partner_usage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> dict:
    """Current month usage, limit, remaining, and overage for the authenticated partner."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    from app.services.api_usage_tracking import get_usage_and_limits

    usage = await get_usage_and_limits(redis, db, str(user.id))
    return usage


@router.get("/billing-summary")
async def get_billing_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
) -> dict:
    """Combined plan details, current usage, and recent usage history."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    from app.services.api_usage_tracking import get_usage_and_limits, get_usage_history

    # Entitlement / plan info
    stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == user.id)
    ent = (await db.execute(stmt)).scalar_one_or_none()

    plan = None
    if ent:
        plan = {
            "plan_code": ent.plan_code,
            "api_access_enabled": ent.api_access_enabled,
            "soft_limit_monthly": ent.soft_limit_monthly,
            "overage_enabled": ent.overage_enabled,
            "overage_price_cents": ent.overage_price_cents,
            "overage_unit_quantity": ent.overage_unit_quantity,
        }

    # Current period usage
    current_usage = await get_usage_and_limits(redis, db, str(user.id))

    # Recent history (last 6 months)
    history_rows = await get_usage_history(db, str(user.id), limit=6)
    history = [
        {
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "request_count": row.request_count,
            "included_limit": row.included_limit,
            "overage_count": row.overage_count,
        }
        for row in history_rows
    ]

    return {
        "plan": plan,
        "current_usage": current_usage,
        "history": history,
    }


@router.get("/usage/history")
async def get_partner_usage_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_api_partner),
    limit: int = Query(default=6, ge=1, le=12),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Historical usage periods for the authenticated partner."""
    from app.services.api_usage_tracking import get_usage_history

    rows = await get_usage_history(db, str(user.id), limit=limit, offset=offset)
    return {
        "periods": [
            {
                "period_start": row.period_start.isoformat() if row.period_start else None,
                "period_end": row.period_end.isoformat() if row.period_end else None,
                "request_count": row.request_count,
                "included_limit": row.included_limit,
                "overage_count": row.overage_count,
            }
            for row in rows
        ],
    }


@router.post("/portal")
async def partner_portal_session(
    user: User = Depends(get_current_user),
) -> dict:
    """Create a Stripe billing portal session for API plan management."""
    from app.services.stripe_service import create_customer_portal

    try:
        url = await create_customer_portal(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"url": url}
