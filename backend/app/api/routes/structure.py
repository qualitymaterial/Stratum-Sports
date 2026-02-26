from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.propagation_event import PropagationEvent

router = APIRouter()


@router.get("/live")
async def structure_live(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the latest propagation event per (event_id, market_key)."""

    # Subquery: max created_at per (event_id, market_key)
    from sqlalchemy import func

    latest_sub = (
        select(
            PropagationEvent.event_id,
            PropagationEvent.market_key,
            func.max(PropagationEvent.created_at).label("max_created_at"),
        )
        .group_by(PropagationEvent.event_id, PropagationEvent.market_key)
        .subquery()
    )

    stmt = (
        select(PropagationEvent)
        .join(
            latest_sub,
            (PropagationEvent.event_id == latest_sub.c.event_id)
            & (PropagationEvent.market_key == latest_sub.c.market_key)
            & (PropagationEvent.created_at == latest_sub.c.max_created_at),
        )
        .order_by(PropagationEvent.created_at.desc())
        .limit(200)
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "event_id": row.event_id,
            "market_key": row.market_key,
            "outcome_name": row.outcome_name,
            "origin_venue": row.origin_venue,
            "origin_tier": row.origin_tier,
            "origin_delta": row.origin_delta,
            "adoption_percent": row.adoption_percent,
            "adoption_count": row.adoption_count,
            "total_venues": row.total_venues,
            "dispersion_before": row.dispersion_before,
            "dispersion_after": row.dispersion_after,
            "minutes_to_tip": row.minutes_to_tip,
        }
        for row in rows
    ]
