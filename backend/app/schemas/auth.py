from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=10, max_length=128)


class MessageResponse(BaseModel):
    message: str


class PasswordResetRequestResponse(MessageResponse):
    reset_token: str | None = None
    expires_in_minutes: int | None = None


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    tier: str
    is_admin: bool
    admin_role: str | None = None
    mfa_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginResponse(BaseModel):
    """Union-type response: either a full token or an MFA challenge."""
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserOut | None = None
    mfa_required: bool = False
    mfa_challenge_token: str | None = None


class MfaVerifyRequest(BaseModel):
    """Second phase of MFA login."""
    mfa_challenge_token: str
    mfa_code: str = Field(min_length=6, max_length=8)


# ── MFA management schemas ─────────────────────────────────────


class MfaStatusResponse(BaseModel):
    mfa_enabled: bool
    mfa_enrolled_at: datetime | None = None
    backup_codes_remaining: int


class MfaEnrollStartResponse(BaseModel):
    totp_secret: str
    provisioning_uri: str


class MfaEnrollConfirmRequest(BaseModel):
    totp_code: str = Field(min_length=6, max_length=6)


class MfaEnrollConfirmResponse(BaseModel):
    mfa_enabled: bool = True
    backup_codes: list[str]


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    mfa_code: str = Field(min_length=6, max_length=8)


class MfaRegenerateBackupCodesRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    mfa_code: str = Field(min_length=6, max_length=6)


class MfaRegenerateBackupCodesResponse(BaseModel):
    backup_codes: list[str]


class PasswordPolicyOut(BaseModel):
    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digit: bool
    require_special: bool
