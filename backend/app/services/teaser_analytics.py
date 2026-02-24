import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.teaser_interaction_event import TeaserInteractionEvent
from app.models.user import User

logger = logging.getLogger(__name__)

VIEW_EVENT = "viewed_teaser"
CLICK_EVENT = "clicked_upgrade_from_teaser"


async def persist_teaser_interaction_event(
    db: AsyncSession,
    *,
    user: User,
    event_name: str,
    source: str | None = None,
    sport_key: str | None = None,
) -> None:
    user_id = str(user.id)
    user_tier = str(user.tier)
    user_is_admin = bool(user.is_admin)
    event = TeaserInteractionEvent(
        user_id=user.id,
        event_name=event_name,
        source=source,
        sport_key=sport_key,
        user_tier=user_tier,
        is_admin=user_is_admin,
    )
    try:
        db.add(event)
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning(
            "Failed to persist teaser interaction event",
            extra={
                "event_name": event_name,
                "sport_key": sport_key,
                "source": source,
                "user_id": user_id,
            },
        )


async def get_teaser_conversion_funnel(
    db: AsyncSession,
    *,
    days: int,
) -> dict:
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    views_case = case((TeaserInteractionEvent.event_name == VIEW_EVENT, 1), else_=0)
    clicks_case = case((TeaserInteractionEvent.event_name == CLICK_EVENT, 1), else_=0)
    unique_viewers_case = case(
        (TeaserInteractionEvent.event_name == VIEW_EVENT, TeaserInteractionEvent.user_id),
        else_=None,
    )
    unique_clickers_case = case(
        (TeaserInteractionEvent.event_name == CLICK_EVENT, TeaserInteractionEvent.user_id),
        else_=None,
    )

    try:
        summary_stmt = select(
            func.coalesce(func.sum(views_case), 0).label("teaser_views"),
            func.coalesce(func.sum(clicks_case), 0).label("teaser_clicks"),
            func.count(func.distinct(unique_viewers_case)).label("unique_viewers"),
            func.count(func.distinct(unique_clickers_case)).label("unique_clickers"),
        ).where(TeaserInteractionEvent.created_at >= period_start)
        summary_row = (await db.execute(summary_stmt)).mappings().one()

        sport_key_expr = func.coalesce(TeaserInteractionEvent.sport_key, "unknown")
        by_sport_stmt = (
            select(
                sport_key_expr.label("sport_key"),
                func.coalesce(func.sum(views_case), 0).label("teaser_views"),
                func.coalesce(func.sum(clicks_case), 0).label("teaser_clicks"),
            )
            .where(TeaserInteractionEvent.created_at >= period_start)
            .group_by(sport_key_expr)
            .order_by(func.coalesce(func.sum(views_case), 0).desc(), sport_key_expr.asc())
        )
        by_sport_rows = (await db.execute(by_sport_stmt)).mappings().all()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning(
            "Teaser conversion funnel unavailable; returning zeros",
            extra={"days": days},
        )
        return {
            "days": int(days),
            "period_start": period_start,
            "period_end": period_end,
            "teaser_views": 0,
            "teaser_clicks": 0,
            "click_through_rate": 0.0,
            "unique_viewers": 0,
            "unique_clickers": 0,
            "by_sport": [],
        }

    teaser_views = int(summary_row["teaser_views"] or 0)
    teaser_clicks = int(summary_row["teaser_clicks"] or 0)
    click_through_rate = float(teaser_clicks / teaser_views) if teaser_views > 0 else 0.0

    by_sport: list[dict[str, object]] = []
    for row in by_sport_rows:
        sport_views = int(row["teaser_views"] or 0)
        sport_clicks = int(row["teaser_clicks"] or 0)
        by_sport.append(
            {
                "sport_key": str(row["sport_key"]),
                "teaser_views": sport_views,
                "teaser_clicks": sport_clicks,
                "click_through_rate": float(sport_clicks / sport_views) if sport_views > 0 else 0.0,
            }
        )

    return {
        "days": int(days),
        "period_start": period_start,
        "period_end": period_end,
        "teaser_views": teaser_views,
        "teaser_clicks": teaser_clicks,
        "click_through_rate": click_through_rate,
        "unique_viewers": int(summary_row["unique_viewers"] or 0),
        "unique_clickers": int(summary_row["unique_clickers"] or 0),
        "by_sport": by_sport,
    }
