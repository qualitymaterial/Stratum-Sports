import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()


def _set_stripe_api_key() -> None:
    stripe.api_key = settings.stripe_secret_key


async def create_checkout_session(db: AsyncSession, user: User) -> str:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")

    _set_stripe_api_key()

    if not user.stripe_customer_id:
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
        user.stripe_customer_id = customer["id"]
        await db.commit()
        await db.refresh(user)

    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=user.stripe_customer_id,
        client_reference_id=str(user.id),
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
    )
    return session["url"]


async def create_customer_portal(user: User) -> str:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")
    if not user.stripe_customer_id:
        raise RuntimeError("No Stripe customer found")

    _set_stripe_api_key()
    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=user.stripe_customer_id,
        return_url=settings.stripe_success_url,
    )
    return session["url"]


async def _upsert_subscription(
    db: AsyncSession,
    *,
    user: User,
    stripe_subscription_id: str,
    stripe_price_id: str,
    status: str,
    current_period_end: datetime | None,
    cancel_at_period_end: bool,
) -> Subscription:
    stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    record = (await db.execute(stmt)).scalar_one_or_none()

    if record is None:
        record = Subscription(
            user_id=user.id,
            stripe_customer_id=user.stripe_customer_id or "",
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=stripe_price_id,
            status=status,
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        db.add(record)
    else:
        record.status = status
        record.current_period_end = current_period_end
        record.cancel_at_period_end = cancel_at_period_end
        record.stripe_price_id = stripe_price_id

    user.tier = "pro" if status in {"active", "trialing"} else "free"
    await db.commit()
    await db.refresh(record)
    return record


async def process_webhook_event(
    db: AsyncSession,
    *,
    payload: bytes,
    signature: str | None,
) -> dict:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")

    _set_stripe_api_key()

    if settings.stripe_webhook_secret and signature:
        event = await asyncio.to_thread(
            stripe.Webhook.construct_event,
            payload,
            signature,
            settings.stripe_webhook_secret,
        )
    elif settings.app_env == "development":
        logger.warning("Stripe webhook signature verification skipped (development mode)")
        event = json.loads(payload.decode("utf-8"))
    else:
        raise RuntimeError(
            "Stripe webhook secret is not configured. "
            "Set STRIPE_WEBHOOK_SECRET for production use."
        )

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            user = await db.get(User, UUID(user_id))
            if user is not None:
                user.stripe_customer_id = customer_id
                await db.commit()

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        customer_id = data.get("customer")
        subscription_id = data.get("id")
        status = data.get("status", "canceled")
        items = data.get("items", {}).get("data", [])
        price_id = items[0]["price"]["id"] if items else settings.stripe_pro_price_id

        if customer_id and subscription_id:
            stmt = select(User).where(User.stripe_customer_id == customer_id)
            user = (await db.execute(stmt)).scalar_one_or_none()
            if user:
                period_end = data.get("current_period_end")
                current_period_end = (
                    datetime.fromtimestamp(period_end, tz=UTC) if period_end else None
                )
                await _upsert_subscription(
                    db,
                    user=user,
                    stripe_subscription_id=subscription_id,
                    stripe_price_id=price_id,
                    status=status,
                    current_period_end=current_period_end,
                    cancel_at_period_end=bool(data.get("cancel_at_period_end", False)),
                )

    logger.info("Stripe webhook processed", extra={"type": event_type})
    return {"received": True, "type": event_type}
