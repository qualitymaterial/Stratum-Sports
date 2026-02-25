from uuid import UUID
from secrets import compare_digest

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_roles import has_admin_permission, is_admin_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tier import is_pro
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()


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


async def require_pro_user(user: User = Depends(get_current_user)) -> User:
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


def require_ops_token(request: Request) -> None:
    expected = settings.ops_internal_token.strip()
    provided = request.headers.get("X-Stratum-Ops-Token", "")
    if not expected or not compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
