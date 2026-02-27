import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()


def _set_stripe_api_key() -> None:
    stripe.api_key = settings.stripe_secret_key


def _require_stripe_configured() -> None:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")


def _extract_price_id(subscription_payload: dict) -> str:
    items = subscription_payload.get("items", {}).get("data", [])
    if items:
        price = items[0].get("price", {})
        if isinstance(price, dict) and isinstance(price.get("id"), str):
            return price["id"]
    return settings.stripe_pro_price_id


def _extract_period_end(subscription_payload: dict) -> datetime | None:
    period_end = subscription_payload.get("current_period_end")
    if period_end:
        return datetime.fromtimestamp(period_end, tz=UTC)
    return None


async def get_latest_subscription_for_user(db: AsyncSession, user_id: UUID) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.updated_at.desc(), Subscription.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_checkout_session(db: AsyncSession, user: User) -> str:
    _require_stripe_configured()

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


async def create_api_checkout_session(db: AsyncSession, user: User, plan: str) -> str:
    """Create a Stripe checkout session for an API partner plan."""
    _require_stripe_configured()
    _set_stripe_api_key()

    if plan == "annual":
        price_id = settings.stripe_api_annual_price_id
    else:
        price_id = settings.stripe_api_monthly_price_id

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
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.stripe_api_success_url,
        cancel_url=settings.stripe_api_cancel_url,
        metadata={"product_type": "api", "plan_code": plan},
    )
    return session["url"]


async def create_customer_portal(user: User) -> str:
    _require_stripe_configured()
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


async def _sync_api_entitlement(
    db: AsyncSession,
    *,
    user: User,
    status: str,
    plan_code: str,
) -> None:
    """Create or update ApiPartnerEntitlement based on API plan subscription status."""
    stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == user.id)
    ent = (await db.execute(stmt)).scalar_one_or_none()
    previous_access = ent.api_access_enabled if ent else None

    if status in {"active", "trialing"}:
        if ent is None:
            ent = ApiPartnerEntitlement(
                user_id=user.id,
                plan_code=plan_code,
                api_access_enabled=True,
                soft_limit_monthly=10000,
                overage_enabled=True,
                overage_price_cents=100,
                overage_unit_quantity=1000,
            )
            db.add(ent)
            logger.info(
                "API access provisioned",
                extra={
                    "event": "api_access_provisioned",
                    "user_id": str(user.id),
                    "plan_code": plan_code,
                    "subscription_status": status,
                },
            )
        else:
            ent.plan_code = plan_code
            ent.api_access_enabled = True
            if previous_access is False:
                logger.info(
                    "API access restored",
                    extra={
                        "event": "api_access_restored",
                        "user_id": str(user.id),
                        "plan_code": plan_code,
                        "subscription_status": status,
                    },
                )
    else:
        # canceled, unpaid, past_due — disable access, keep plan_code for audit
        if ent is not None:
            ent.api_access_enabled = False
            if previous_access is True:
                logger.warning(
                    "API access suspended",
                    extra={
                        "event": "api_access_suspended",
                        "user_id": str(user.id),
                        "plan_code": ent.plan_code,
                        "subscription_status": status,
                        "reason": "subscription_status_change",
                    },
                )

    await db.commit()


async def process_webhook_event(
    db: AsyncSession,
    *,
    payload: bytes,
    signature: str | None,
) -> dict:
    _require_stripe_configured()

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

    logger.info(
        "Stripe webhook received",
        extra={
            "event": "stripe_webhook_received",
            "event_type": event_type,
            "stripe_event_id": event.get("id"),
        },
    )

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            user = await db.get(User, UUID(user_id))
            if user is not None:
                user.stripe_customer_id = customer_id
                await db.commit()
                logger.info(
                    "Stripe customer linked",
                    extra={
                        "event": "stripe_customer_linked",
                        "user_id": user_id,
                        "stripe_customer_id": customer_id,
                    },
                )
            else:
                logger.warning(
                    "Checkout session user not found",
                    extra={
                        "event": "stripe_webhook_user_not_found",
                        "user_id": user_id,
                        "event_type": event_type,
                    },
                )

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

        api_price_ids = {settings.stripe_api_monthly_price_id, settings.stripe_api_annual_price_id}

        if not customer_id or not subscription_id:
            logger.warning(
                "Webhook missing customer_id or subscription_id",
                extra={
                    "event": "stripe_webhook_incomplete_data",
                    "event_type": event_type,
                    "has_customer_id": bool(customer_id),
                    "has_subscription_id": bool(subscription_id),
                },
            )

        if customer_id and subscription_id:
            stmt = select(User).where(User.stripe_customer_id == customer_id)
            user = (await db.execute(stmt)).scalar_one_or_none()
            if not user:
                logger.warning(
                    "Webhook customer not matched to user",
                    extra={
                        "event": "stripe_webhook_customer_unmatched",
                        "stripe_customer_id": customer_id,
                        "subscription_id": subscription_id,
                        "event_type": event_type,
                    },
                )
            if user:
                logger.info(
                    "Processing subscription event",
                    extra={
                        "event": "stripe_subscription_processing",
                        "event_type": event_type,
                        "user_id": str(user.id),
                        "subscription_id": subscription_id,
                        "price_id": price_id,
                        "status": status,
                        "is_api_plan": price_id in api_price_ids,
                    },
                )
                if price_id in api_price_ids:
                    # API plan subscription — sync entitlement, don't change user.tier
                    plan_code = (
                        "api_monthly"
                        if price_id == settings.stripe_api_monthly_price_id
                        else "api_annual"
                    )
                    await _sync_api_entitlement(
                        db, user=user, status=status, plan_code=plan_code,
                    )
                else:
                    # Pro web subscription — existing behavior
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

    logger.info(
        "Stripe webhook processed",
        extra={"event": "stripe_webhook_processed", "event_type": event_type},
    )
    return {"received": True, "type": event_type}


async def admin_resync_user_subscription(
    db: AsyncSession,
    *,
    user: User,
) -> Subscription | None:
    _require_stripe_configured()
    if not user.stripe_customer_id:
        raise ValueError("User has no Stripe customer ID")

    _set_stripe_api_key()
    result = await asyncio.to_thread(
        stripe.Subscription.list,
        customer=user.stripe_customer_id,
        status="all",
        limit=20,
    )
    rows = list(result.get("data") or [])
    if not rows:
        user.tier = "free"
        await db.commit()
        return None

    chosen = max(rows, key=lambda item: int(item.get("created") or 0))
    subscription_id = str(chosen.get("id") or "")
    if not subscription_id:
        raise ValueError("Stripe subscription payload missing id")
    return await _upsert_subscription(
        db,
        user=user,
        stripe_subscription_id=subscription_id,
        stripe_price_id=_extract_price_id(chosen),
        status=str(chosen.get("status") or "canceled"),
        current_period_end=_extract_period_end(chosen),
        cancel_at_period_end=bool(chosen.get("cancel_at_period_end", False)),
    )


async def admin_cancel_user_subscription(
    db: AsyncSession,
    *,
    user: User,
) -> Subscription:
    _require_stripe_configured()
    local = await get_latest_subscription_for_user(db, user.id)
    if local is None:
        raise ValueError("No local subscription found for user")

    _set_stripe_api_key()
    updated = await asyncio.to_thread(
        stripe.Subscription.modify,
        local.stripe_subscription_id,
        cancel_at_period_end=True,
    )
    return await _upsert_subscription(
        db,
        user=user,
        stripe_subscription_id=str(updated.get("id") or local.stripe_subscription_id),
        stripe_price_id=_extract_price_id(updated),
        status=str(updated.get("status") or local.status),
        current_period_end=_extract_period_end(updated) or local.current_period_end,
        cancel_at_period_end=bool(updated.get("cancel_at_period_end", True)),
    )


async def admin_reactivate_user_subscription(
    db: AsyncSession,
    *,
    user: User,
) -> Subscription:
    _require_stripe_configured()
    local = await get_latest_subscription_for_user(db, user.id)
    if local is None:
        raise ValueError("No local subscription found for user")

    _set_stripe_api_key()
    updated = await asyncio.to_thread(
        stripe.Subscription.modify,
        local.stripe_subscription_id,
        cancel_at_period_end=False,
    )
    return await _upsert_subscription(
        db,
        user=user,
        stripe_subscription_id=str(updated.get("id") or local.stripe_subscription_id),
        stripe_price_id=_extract_price_id(updated),
        status=str(updated.get("status") or local.status),
        current_period_end=_extract_period_end(updated) or local.current_period_end,
        cancel_at_period_end=bool(updated.get("cancel_at_period_end", False)),
    )
