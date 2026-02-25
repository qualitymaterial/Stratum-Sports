from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog


async def write_admin_audit_log(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    action_type: str,
    target_type: str,
    reason: str,
    target_id: str | None = None,
    before_payload: Mapping | None = None,
    after_payload: Mapping | None = None,
    request_id: str | None = None,
) -> AdminAuditLog:
    audit = AdminAuditLog(
        actor_user_id=actor_user_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before_payload=dict(before_payload) if before_payload is not None else None,
        after_payload=dict(after_payload) if after_payload is not None else None,
        request_id=request_id,
    )
    db.add(audit)
    await db.flush()
    return audit
