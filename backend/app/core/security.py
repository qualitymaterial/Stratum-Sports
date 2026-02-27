import secrets
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

import bcrypt

settings = get_settings()


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def validate_password_strength(password: str) -> list[str]:
    """Return list of policy violation messages. Empty list means valid."""
    import re
    s = get_settings()
    errors: list[str] = []
    if len(password) < s.password_min_length:
        errors.append(f"Password must be at least {s.password_min_length} characters")
    if s.password_require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if s.password_require_lowercase and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if s.password_require_digit and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")
    if s.password_require_special and not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must contain at least one special character")
    return errors


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire, "iat": datetime.now(UTC)}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def create_mfa_challenge_token(user_id: str) -> str:
    """Create a short-lived token for MFA challenge (password verified, MFA pending)."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.mfa_challenge_token_expire_minutes)
    to_encode: dict[str, Any] = {
        "type": "mfa_challenge",
        "sub": user_id,
        "nonce": secrets.token_urlsafe(16),
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_mfa_challenge_token(token: str) -> dict[str, Any] | None:
    """Decode and validate an MFA challenge token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != "mfa_challenge":
        return None
    if "sub" not in payload:
        return None
    return payload


def create_oauth_state_token(provider: str, expires_minutes: int = 10) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    to_encode: dict[str, Any] = {
        "type": "oauth_state",
        "provider": provider,
        "nonce": secrets.token_urlsafe(24),
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(token: str, provider: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    if payload.get("type") != "oauth_state":
        return None
    if payload.get("provider") != provider:
        return None
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 16:
        return None
    return payload


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(48)


def hash_password_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
