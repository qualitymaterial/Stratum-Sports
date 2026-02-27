from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from pydantic import BaseModel

from app.services.stripe_service import (
    create_api_checkout_session,
    create_checkout_session,
    create_customer_portal,
    process_webhook_event,
)

router = APIRouter()


class ApiCheckoutRequest(BaseModel):
    plan: str = "monthly"


@router.post("/create-api-checkout-session")
async def api_checkout_session(
    body: ApiCheckoutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if body.plan not in {"monthly", "annual"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="plan must be 'monthly' or 'annual'",
        )
    try:
        url = await create_api_checkout_session(db, user, body.plan)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"url": url}


@router.post("/create-checkout-session")
async def checkout_session(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        url = await create_checkout_session(db, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"url": url}


@router.post("/portal")
async def portal_session(user: User = Depends(get_current_user)) -> dict:
    try:
        url = await create_customer_portal(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    payload = await request.body()
    try:
        result = await process_webhook_event(
            db,
            payload=payload,
            signature=stripe_signature,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result
