import hashlib
import secrets
from datetime import UTC, datetime

import pyotp
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mfa_backup_code import MfaBackupCode

TOTP_ISSUER = "Stratum Sports"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8  # 8 hex chars (4 bytes)


def generate_totp_secret() -> str:
    """Generate a new TOTP secret (base32-encoded)."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, email: str) -> str:
    """Generate the otpauth:// URI for QR code display."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a TOTP code with a 1-window tolerance (30s before/after)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


def _hash_backup_code(code: str) -> str:
    """Hash a backup code with SHA-256."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_backup_codes() -> list[str]:
    """Generate a set of plaintext backup codes."""
    return [secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper() for _ in range(BACKUP_CODE_COUNT)]


async def store_backup_codes(db: AsyncSession, user_id: object, codes: list[str]) -> None:
    """Hash and store backup codes, replacing any existing unused codes."""
    now = datetime.now(UTC)
    await db.execute(
        update(MfaBackupCode)
        .where(
            MfaBackupCode.user_id == user_id,
            MfaBackupCode.used_at.is_(None),
        )
        .values(used_at=now)
    )

    for code in codes:
        db.add(MfaBackupCode(
            user_id=user_id,
            code_hash=_hash_backup_code(code),
        ))
    await db.flush()


async def verify_backup_code(db: AsyncSession, user_id: object, code: str) -> bool:
    """Verify and consume a backup code. Returns True if valid."""
    code_hash = _hash_backup_code(code.strip().upper())
    stmt = (
        select(MfaBackupCode)
        .where(
            MfaBackupCode.user_id == user_id,
            MfaBackupCode.code_hash == code_hash,
            MfaBackupCode.used_at.is_(None),
        )
        .limit(1)
    )
    backup_code = (await db.execute(stmt)).scalar_one_or_none()
    if backup_code is None:
        return False
    backup_code.used_at = datetime.now(UTC)
    await db.flush()
    return True


async def remaining_backup_codes_count(db: AsyncSession, user_id: object) -> int:
    """Count remaining unused backup codes for a user."""
    stmt = select(func.count(MfaBackupCode.id)).where(
        MfaBackupCode.user_id == user_id,
        MfaBackupCode.used_at.is_(None),
    )
    return int((await db.execute(stmt)).scalar() or 0)
