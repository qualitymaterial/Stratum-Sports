import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_user
from app.core.database import get_db
from app.core.security import verify_password
from app.models.user import User
from app.schemas.auth import (
    MfaDisableRequest,
    MfaEnrollConfirmRequest,
    MfaEnrollConfirmResponse,
    MfaEnrollStartResponse,
    MfaRegenerateBackupCodesRequest,
    MfaRegenerateBackupCodesResponse,
    MfaStatusResponse,
    MessageResponse,
)
from app.services.admin_audit import write_admin_audit_log
from app.services.admin_mfa import (
    generate_backup_codes,
    generate_totp_secret,
    get_totp_provisioning_uri,
    remaining_backup_codes_count,
    store_backup_codes,
    verify_totp_code,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status", response_model=MfaStatusResponse)
async def mfa_status(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_user),
) -> MfaStatusResponse:
    remaining = await remaining_backup_codes_count(db, admin_user.id) if admin_user.mfa_enabled else 0
    return MfaStatusResponse(
        mfa_enabled=admin_user.mfa_enabled,
        mfa_enrolled_at=admin_user.mfa_enrolled_at,
        backup_codes_remaining=remaining,
    )


@router.post("/enroll/start", response_model=MfaEnrollStartResponse)
async def mfa_enroll_start(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_user),
) -> MfaEnrollStartResponse:
    if admin_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is already enabled")

    secret = generate_totp_secret()
    admin_user.mfa_secret_encrypted = secret
    await db.commit()

    provisioning_uri = get_totp_provisioning_uri(secret, admin_user.email)
    return MfaEnrollStartResponse(totp_secret=secret, provisioning_uri=provisioning_uri)


@router.post("/enroll/confirm", response_model=MfaEnrollConfirmResponse)
async def mfa_enroll_confirm(
    payload: MfaEnrollConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_user),
) -> MfaEnrollConfirmResponse:
    if admin_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is already enabled")
    if not admin_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start MFA enrollment first")

    if not verify_totp_code(admin_user.mfa_secret_encrypted, payload.totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")

    admin_user.mfa_enabled = True
    admin_user.mfa_enrolled_at = datetime.now(UTC)

    backup_codes = generate_backup_codes()
    await store_backup_codes(db, admin_user.id, backup_codes)

    await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.mfa.enrolled",
        target_type="user",
        target_id=str(admin_user.id),
        reason="Admin enrolled in MFA",
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()

    logger.info("admin_mfa_enrolled", extra={"user_id": str(admin_user.id)})
    return MfaEnrollConfirmResponse(backup_codes=backup_codes)


@router.post("/disable", response_model=MessageResponse)
async def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_user),
) -> MessageResponse:
    if not admin_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    if not verify_password(payload.password, admin_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    if not admin_user.mfa_secret_encrypted or not verify_totp_code(admin_user.mfa_secret_encrypted, payload.mfa_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    admin_user.mfa_enabled = False
    admin_user.mfa_secret_encrypted = None
    admin_user.mfa_enrolled_at = None

    await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.mfa.disabled",
        target_type="user",
        target_id=str(admin_user.id),
        reason="Admin disabled MFA",
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()

    logger.info("admin_mfa_disabled", extra={"user_id": str(admin_user.id)})
    return MessageResponse(message="MFA has been disabled")


@router.post("/backup-codes/regenerate", response_model=MfaRegenerateBackupCodesResponse)
async def mfa_regenerate_backup_codes(
    payload: MfaRegenerateBackupCodesRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin_user),
) -> MfaRegenerateBackupCodesResponse:
    if not admin_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    if not verify_password(payload.password, admin_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    if not admin_user.mfa_secret_encrypted or not verify_totp_code(admin_user.mfa_secret_encrypted, payload.mfa_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    backup_codes = generate_backup_codes()
    await store_backup_codes(db, admin_user.id, backup_codes)

    await write_admin_audit_log(
        db,
        actor_user_id=admin_user.id,
        action_type="admin.mfa.backup_codes_regenerated",
        target_type="user",
        target_id=str(admin_user.id),
        reason="Admin regenerated MFA backup codes",
        request_id=request.headers.get("x-request-id"),
    )
    await db.commit()

    return MfaRegenerateBackupCodesResponse(backup_codes=backup_codes)
