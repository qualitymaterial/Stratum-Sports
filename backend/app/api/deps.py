from dataclasses import dataclass, field
from datetime import UTC, datetime
from secrets import compare_digest
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_roles import has_admin_permission, is_admin_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.core.tier import is_pro
from app.models.api_partner_entitlement import ApiPartnerEntitlement
from app.models.api_partner_key import ApiPartnerKey
from app.models.user import User
from app.services.partner_api_keys import API_KEY_PREFIX, hash_partner_api_key

bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()


async def _authenticate_api_key(
    raw_token: str,
    db: AsyncSession,
) -> tuple[User, ApiPartnerKey]:
    """Authenticate a request via API partner key (stratum_pk_...)."""
    key_hash = hash_partner_api_key(raw_token)
    stmt = select(ApiPartnerKey).where(ApiPartnerKey.key_hash == key_hash)
    key = (await db.execute(stmt)).scalar_one_or_none()

    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if not key.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key revoked")
    if key.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key revoked")
    if key.expires_at is not None and key.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")

    user = await db.get(User, key.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    # Check entitlement
    ent_stmt = select(ApiPartnerEntitlement).where(ApiPartnerEntitlement.user_id == key.user_id)
    entitlement = (await db.execute(ent_stmt)).scalar_one_or_none()
    if entitlement is None or not entitlement.api_access_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API access not enabled")

    # Update last_used_at (best-effort, non-blocking)
    key.last_used_at = datetime.now(UTC)

    return user, key


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = UUID(payload["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


async def get_current_user_or_api_partner(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via JWT or API partner key (stratum_pk_ prefix)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    raw_token = credentials.credentials

    if raw_token.startswith(API_KEY_PREFIX):
        user, key = await _authenticate_api_key(raw_token, db)
        request.state.auth_method = "api_key"
        request.state.api_partner_key_id = str(key.id)
        request.state.api_partner_user_id = str(user.id)
        return user

    # JWT path
    request.state.auth_method = "jwt"
    payload = decode_token(raw_token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = UUID(payload["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


async def require_pro_user(user: User = Depends(get_current_user)) -> User:
    if not is_pro(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required",
        )
    return user


async def require_pro_or_api_partner(
    request: Request,
    user: User = Depends(get_current_user_or_api_partner),
) -> User:
    """Allow access if user is Pro (JWT) or authenticated via API partner key."""
    auth_method = getattr(request.state, "auth_method", "jwt")
    if auth_method == "api_key":
        return user  # entitlement already validated in _authenticate_api_key
    if not is_pro(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required",
        )
    return user


async def require_admin_user(user: User = Depends(get_current_user)) -> User:
    if not is_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_admin_permission(permission: str):
    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if not has_admin_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient admin permissions",
            )
        return user

    return _dependency


@dataclass
class OpsTokenIdentity:
    """Identity info for an authenticated ops token caller."""

    source: str  # "service_token" or "static_token"
    token_name: str | None = None
    token_id: str | None = None
    scopes: list[str] = field(default_factory=list)


async def require_ops_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> OpsTokenIdentity:
    provided = request.headers.get("X-Stratum-Ops-Token", "").strip()
    if not provided:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Try DB-backed service token first (ops prefix)
    if provided.startswith("stratum_ops_"):
        from app.services.ops_service_tokens import authenticate_ops_service_token

        try:
            token = await authenticate_ops_service_token(db, provided)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            ) from exc

        identity = OpsTokenIdentity(
            source="service_token",
            token_name=token.name,
            token_id=str(token.id),
            scopes=list(token.scopes),
        )
        request.state.ops_identity = identity
        return identity

    # Fall back to static token comparison
    expected = settings.ops_internal_token.strip()
    if not expected or not compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    identity = OpsTokenIdentity(
        source="static_token",
        token_name=None,
        token_id=None,
        scopes=[],  # static token: all-access, no scope restriction
    )
    request.state.ops_identity = identity
    return identity


def require_ops_scope(scope: str):
    """Factory that returns a dependency checking a specific ops scope."""

    async def _check_scope(
        identity: OpsTokenIdentity = Depends(require_ops_token),
    ) -> OpsTokenIdentity:
        # Static tokens bypass scope checks (backward compat)
        if identity.source == "static_token":
            return identity
        if scope not in identity.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token lacks required scope: {scope}",
            )
        return identity

    return _check_scope
