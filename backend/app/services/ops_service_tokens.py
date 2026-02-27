import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_service_token import OpsServiceToken

OPS_KEY_PREFIX = "stratum_ops_"
OPS_KEY_PREFIX_LEN = 16

SCOPE_OPS_READ = "ops:read"
SCOPE_OPS_WRITE = "ops:write"
VALID_OPS_SCOPES = {SCOPE_OPS_READ, SCOPE_OPS_WRITE}


def hash_ops_service_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _public_key_prefix(raw_key: str) -> str:
    return raw_key[:OPS_KEY_PREFIX_LEN]


def serialize_ops_service_token_for_audit(token: OpsServiceToken) -> dict:
    return {
        "id": str(token.id),
        "name": token.name,
        "key_prefix": token.key_prefix,
        "scopes": list(token.scopes),
        "is_active": token.is_active,
        "expires_at": token.expires_at.isoformat() if token.expires_at is not None else None,
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at is not None else None,
        "revoked_at": token.revoked_at.isoformat() if token.revoked_at is not None else None,
    }


def validate_scopes(scopes: list[str]) -> list[str]:
    clean = list(dict.fromkeys(s.strip() for s in scopes))
    invalid = [s for s in clean if s not in VALID_OPS_SCOPES]
    if invalid:
        raise ValueError(f"Unknown scopes: {invalid}")
    if not clean:
        raise ValueError("At least one scope is required")
    return clean


async def list_ops_service_tokens(db: AsyncSession) -> list[OpsServiceToken]:
    stmt = select(OpsServiceToken).order_by(OpsServiceToken.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def get_ops_service_token(db: AsyncSession, token_id: UUID) -> OpsServiceToken | None:
    return await db.get(OpsServiceToken, token_id)


async def issue_ops_service_token(
    db: AsyncSession,
    *,
    created_by_user_id: UUID,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[OpsServiceToken, str]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Token name is required")
    validated_scopes = validate_scopes(scopes)

    raw_key: str | None = None
    key_hash: str | None = None
    for _ in range(5):
        candidate = f"{OPS_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        candidate_hash = hash_ops_service_key(candidate)
        existing = (
            await db.execute(
                select(OpsServiceToken.id).where(OpsServiceToken.key_hash == candidate_hash)
            )
        ).scalar_one_or_none()
        if existing is None:
            raw_key = candidate
            key_hash = candidate_hash
            break
    if raw_key is None or key_hash is None:
        raise RuntimeError("Unable to generate a unique ops service key")

    token = OpsServiceToken(
        created_by_user_id=created_by_user_id,
        name=clean_name,
        key_prefix=_public_key_prefix(raw_key),
        key_hash=key_hash,
        scopes=validated_scopes,
        is_active=True,
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token, raw_key


async def revoke_ops_service_token(
    db: AsyncSession,
    *,
    token: OpsServiceToken,
    revoked_at: datetime | None = None,
) -> OpsServiceToken:
    token.is_active = False
    token.revoked_at = revoked_at or datetime.now(UTC)
    await db.flush()
    await db.refresh(token)
    return token


async def rotate_ops_service_token(
    db: AsyncSession,
    *,
    token: OpsServiceToken,
    created_by_user_id: UUID,
    name: str | None = None,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[OpsServiceToken, str]:
    if not token.is_active:
        raise ValueError("Only active tokens can be rotated")

    await revoke_ops_service_token(db, token=token)
    next_name = (name or token.name).strip()
    next_scopes = scopes if scopes is not None else list(token.scopes)
    next_expires_at = expires_at if expires_at is not None else token.expires_at
    return await issue_ops_service_token(
        db,
        created_by_user_id=created_by_user_id,
        name=next_name,
        scopes=next_scopes,
        expires_at=next_expires_at,
    )


async def authenticate_ops_service_token(
    db: AsyncSession, raw_key: str
) -> OpsServiceToken:
    key_hash = hash_ops_service_key(raw_key)
    stmt = select(OpsServiceToken).where(OpsServiceToken.key_hash == key_hash)
    token = (await db.execute(stmt)).scalar_one_or_none()

    if token is None:
        raise ValueError("Invalid ops service token")
    if not token.is_active:
        raise ValueError("Ops service token has been revoked")
    if token.revoked_at is not None:
        raise ValueError("Ops service token has been revoked")
    if token.expires_at is not None and token.expires_at < datetime.now(UTC):
        raise ValueError("Ops service token has expired")

    token.last_used_at = datetime.now(UTC)
    return token
