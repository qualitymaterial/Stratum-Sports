"""Partner self-serve endpoints for API usage visibility and billing."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_or_api_partner
from app.core.database import get_db
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.user import User

router = APIRouter()


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
