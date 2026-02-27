from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    generate_password_reset_token,
    get_password_hash,
    hash_password_reset_token,
    validate_password_strength,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MfaVerifyRequest,
    PasswordPolicyOut,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.admin_mfa import verify_backup_code, verify_totp_code

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    policy_errors = validate_password_strength(payload.password)
    if policy_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(policy_errors))

    existing_stmt = select(User).where(User.email == payload.email.lower())
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=get_password_hash(payload.password),
        tier="free",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    stmt = select(User).where(User.email == payload.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Track last login
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    # If MFA is enabled, return a challenge token instead of a full access token
    if user.mfa_enabled and user.mfa_secret_encrypted:
        challenge_token = create_mfa_challenge_token(str(user.id))
        return LoginResponse(mfa_required=True, mfa_challenge_token=challenge_token)

    # No MFA — issue full access token
    extra_claims: dict[str, object] = {"mfa": False}
    expires_delta = None
    if user.is_admin:
        extra_claims["adm"] = True
        expires_delta = timedelta(minutes=settings.admin_access_token_expire_minutes)

    token = create_access_token(str(user.id), expires_delta=expires_delta, extra_claims=extra_claims)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login/mfa-verify", response_model=TokenResponse)
async def mfa_verify(payload: MfaVerifyRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Second phase of MFA login: verify TOTP code against challenge token."""
    settings = get_settings()
    challenge = decode_mfa_challenge_token(payload.mfa_challenge_token)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA challenge")

    from uuid import UUID
    user_id = UUID(challenge["sub"])
    user = await db.get(User, user_id)
    if not user or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA challenge")

    # Try TOTP code first, then backup code
    code = payload.mfa_code.strip()
    valid = False
    if len(code) == 6 and user.mfa_secret_encrypted and verify_totp_code(user.mfa_secret_encrypted, code):
        valid = True
    elif await verify_backup_code(db, user.id, code):
        valid = True

    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    # Issue full access token with MFA verified
    extra_claims: dict[str, object] = {"mfa": True}
    expires_delta = None
    if user.is_admin:
        extra_claims["adm"] = True
        expires_delta = timedelta(minutes=settings.admin_access_token_expire_minutes)

    token = create_access_token(str(user.id), expires_delta=expires_delta, extra_claims=extra_claims)
    await db.commit()
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> PasswordResetRequestResponse:
    settings = get_settings()
    generic_message = "If this email exists, a password reset was requested."
    stmt = select(User).where(User.email == payload.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or user.password_hash is None or not user.is_active:
        return PasswordResetRequestResponse(message=generic_message)

    now = datetime.now(UTC)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )

    raw_token = generate_password_reset_token()
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_password_reset_token(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
    )
    db.add(token)
    await db.commit()

    if settings.app_env != "production":
        return PasswordResetRequestResponse(
            message=generic_message,
            reset_token=raw_token,
            expires_in_minutes=settings.password_reset_token_expire_minutes,
        )
    return PasswordResetRequestResponse(message=generic_message)


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    now = datetime.now(UTC)
    token_hash = hash_password_reset_token(payload.token.strip())
    token_stmt = (
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at >= now,
        )
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    reset_token = (await db.execute(token_stmt)).scalar_one_or_none()
    if reset_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        )

    user = await db.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token is invalid")

    policy_errors = validate_password_strength(payload.new_password)
    if policy_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(policy_errors))

    user.password_hash = get_password_hash(payload.new_password)
    reset_token.used_at = now
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != reset_token.id,
        )
        .values(used_at=now)
    )
    await db.commit()
    return MessageResponse(message="Password reset successful")


@router.get("/password-policy", response_model=PasswordPolicyOut)
async def get_password_policy() -> PasswordPolicyOut:
    """Public endpoint so the registration form can display password rules."""
    settings = get_settings()
    return PasswordPolicyOut(
        min_length=settings.password_min_length,
        require_uppercase=settings.password_require_uppercase,
        require_lowercase=settings.password_require_lowercase,
        require_digit=settings.password_require_digit,
        require_special=settings.password_require_special,
    )
