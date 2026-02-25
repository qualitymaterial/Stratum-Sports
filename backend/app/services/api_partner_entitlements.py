from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_partner_entitlement import ApiPartnerEntitlement

API_PARTNER_PLAN_MONTHLY = "api_monthly"
API_PARTNER_PLAN_ANNUAL = "api_annual"
API_PARTNER_PLAN_CODES = {
    API_PARTNER_PLAN_MONTHLY,
    API_PARTNER_PLAN_ANNUAL,
}
DEFAULT_OVERAGE_UNIT_QUANTITY = 1000


async def get_api_partner_entitlement(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> ApiPartnerEntitlement | None:
    stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_or_create_api_partner_entitlement(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> ApiPartnerEntitlement:
    existing = await get_api_partner_entitlement(db, user_id=user_id)
    if existing is not None:
        return existing
    created = ApiPartnerEntitlement(
        user_id=user_id,
        api_access_enabled=False,
        overage_enabled=True,
        overage_unit_quantity=DEFAULT_OVERAGE_UNIT_QUANTITY,
    )
    db.add(created)
    await db.flush()
    return created


def serialize_api_partner_entitlement_for_audit(
    entitlement: ApiPartnerEntitlement,
) -> dict:
    return {
        "id": str(entitlement.id),
        "user_id": str(entitlement.user_id),
        "plan_code": entitlement.plan_code,
        "api_access_enabled": entitlement.api_access_enabled,
        "soft_limit_monthly": entitlement.soft_limit_monthly,
        "overage_enabled": entitlement.overage_enabled,
        "overage_price_cents": entitlement.overage_price_cents,
        "overage_unit_quantity": entitlement.overage_unit_quantity,
    }
