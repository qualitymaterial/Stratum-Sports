"""Flush Redis usage counters to DB and publish Stripe meter events for overage."""

import asyncio
import logging
from datetime import UTC, datetime

import stripe
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.user import User
from app.services.api_usage_tracking import flush_usage_to_db

logger = logging.getLogger(__name__)


async def flush_and_sync_all(redis) -> dict:
    """Flush all active partners' Redis counters to DB. Publish Stripe meter events for overage."""
    settings = get_settings()
    if not settings.api_usage_tracking_enabled:
        return {"flushed": 0, "metered": 0, "errors": 0}

    flushed = 0
    metered = 0
    errors = 0

    async with AsyncSessionLocal() as db:
        stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.api_access_enabled.is_(True))
        entitlements = list((await db.execute(stmt)).scalars().all())

        for ent in entitlements:
            try:
                period = await flush_usage_to_db(db, redis, str(ent.user_id))
                if period is not None:
                    flushed += 1

                    # Publish Stripe meter event if overage exists
                    if period.overage_count > 0 and period.stripe_meter_synced_at is None:
                        user = await db.get(User, ent.user_id)
                        if user and user.stripe_customer_id:
                            try:
                                await asyncio.to_thread(
                                    _create_stripe_meter_event,
                                    customer_id=user.stripe_customer_id,
                                    event_name=settings.stripe_api_meter_event_name,
                                    value=period.overage_count,
                                )
                                period.stripe_meter_synced_at = datetime.now(UTC)
                                await db.commit()
                                metered += 1
                                logger.info(
                                    "Stripe meter event published",
                                    extra={
                                        "user_id": str(ent.user_id),
                                        "overage_count": period.overage_count,
                                    },
                                )
                            except Exception:
                                errors += 1
                                logger.exception(
                                    "Stripe meter event publish failed",
                                    extra={"user_id": str(ent.user_id)},
                                )
            except Exception:
                errors += 1
                logger.exception(
                    "Usage flush failed for user",
                    extra={"user_id": str(ent.user_id)},
                )

    return {"flushed": flushed, "metered": metered, "errors": errors}


def _create_stripe_meter_event(
    *,
    customer_id: str,
    event_name: str,
    value: int,
) -> None:
    """Synchronous Stripe API call (run via asyncio.to_thread)."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        logger.warning("Stripe secret key not configured; skipping meter event")
        return

    stripe.api_key = settings.stripe_secret_key
    stripe.billing.MeterEvent.create(
        event_name=event_name,
        payload={
            "stripe_customer_id": customer_id,
            "value": str(value),
        },
    )
