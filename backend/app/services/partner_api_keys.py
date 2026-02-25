import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_partner_key import ApiPartnerKey

API_KEY_PREFIX = "stratum_pk_"
API_KEY_PREFIX_LEN = 16


def hash_partner_api_key(raw_api_key: str) -> str:
    return hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()


def _public_key_prefix(raw_api_key: str) -> str:
    return raw_api_key[:API_KEY_PREFIX_LEN]


def serialize_api_partner_key_for_audit(key: ApiPartnerKey) -> dict:
    return {
        "id": str(key.id),
        "name": key.name,
        "key_prefix": key.key_prefix,
        "is_active": key.is_active,
        "expires_at": key.expires_at.isoformat() if key.expires_at is not None else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at is not None else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at is not None else None,
    }


async def list_api_partner_keys_for_user(db: AsyncSession, user_id: UUID) -> list[ApiPartnerKey]:
    stmt = (
        select(ApiPartnerKey)
        .where(ApiPartnerKey.user_id == user_id)
        .order_by(ApiPartnerKey.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def issue_api_partner_key(
    db: AsyncSession,
    *,
    user_id: UUID,
    created_by_user_id: UUID,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[ApiPartnerKey, str]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Key name is required")

    raw_api_key: str | None = None
    key_hash: str | None = None
    for _ in range(5):
        candidate = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        candidate_hash = hash_partner_api_key(candidate)
        existing = (
            await db.execute(select(ApiPartnerKey.id).where(ApiPartnerKey.key_hash == candidate_hash))
        ).scalar_one_or_none()
        if existing is None:
            raw_api_key = candidate
            key_hash = candidate_hash
            break
    if raw_api_key is None or key_hash is None:
        raise RuntimeError("Unable to generate a unique API key")

    key = ApiPartnerKey(
        user_id=user_id,
        created_by_user_id=created_by_user_id,
        name=clean_name,
        key_prefix=_public_key_prefix(raw_api_key),
        key_hash=key_hash,
        is_active=True,
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(key)
    await db.flush()
    await db.refresh(key)
    return key, raw_api_key


async def revoke_api_partner_key(
    db: AsyncSession,
    *,
    key: ApiPartnerKey,
    revoked_at: datetime | None = None,
) -> ApiPartnerKey:
    key.is_active = False
    key.revoked_at = revoked_at or datetime.now(UTC)
    await db.flush()
    await db.refresh(key)
    return key


async def rotate_api_partner_key(
    db: AsyncSession,
    *,
    key: ApiPartnerKey,
    created_by_user_id: UUID,
    name: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[ApiPartnerKey, str]:
    if not key.is_active:
        raise ValueError("Only active keys can be rotated")

    await revoke_api_partner_key(db, key=key)
    next_name = (name or key.name).strip()
    next_expires_at = expires_at if expires_at is not None else key.expires_at
    return await issue_api_partner_key(
        db,
        user_id=key.user_id,
        created_by_user_id=created_by_user_id,
        name=next_name,
        expires_at=next_expires_at,
    )
