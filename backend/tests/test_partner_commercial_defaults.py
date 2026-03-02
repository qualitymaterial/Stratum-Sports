from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.user import User
from app.services import api_usage_tracking as usage_service
from app.services import stripe_service


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._values[key] = str(value)
        return True


async def test_sync_api_entitlement_uses_partner_commercial_defaults(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    user = User(email="ent-defaults@example.com", password_hash="x", tier="free")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    monkeypatch.setattr(stripe_service.settings, "partner_soft_limit_monthly", 50000)
    monkeypatch.setattr(stripe_service.settings, "partner_overage_price_cents", 200)

    await stripe_service._sync_api_entitlement(
        db_session,
        user=user,
        status="active",
        plan_code="api_monthly",
    )

    ent = (
        await db_session.execute(
            select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == user.id)
        )
    ).scalar_one()
    assert ent.soft_limit_monthly == 50000
    assert ent.overage_price_cents == 200


async def test_get_usage_and_limits_caches_configured_partner_rate_limit(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    user = User(email="usage-defaults@example.com", password_hash="x", tier="free")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entitlement = ApiPartnerEntitlement(
        user_id=user.id,
        plan_code="api_monthly",
        api_access_enabled=True,
        soft_limit_monthly=50000,
        overage_enabled=True,
        overage_price_cents=200,
        overage_unit_quantity=1000,
    )
    db_session.add(entitlement)
    await db_session.commit()

    fake_settings = SimpleNamespace(
        api_usage_redis_key_prefix="api_usage",
        partner_rate_limit_per_minute=120,
    )
    monkeypatch.setattr(usage_service, "get_settings", lambda: fake_settings)

    redis = _FakeRedis()
    payload = await usage_service.get_usage_and_limits(redis, db_session, str(user.id))
    assert payload["included_limit"] == 50000

    cached_rate_limit = await usage_service.get_cached_rate_limit(redis, str(user.id))
    assert cached_rate_limit == 120
