"""Partner self-serve endpoints for API usage visibility."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_or_api_partner
from app.core.database import get_db
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
