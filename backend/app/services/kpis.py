import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.cycle_kpi import CycleKpi

logger = logging.getLogger(__name__)


def _sanitize_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _sanitize_signals_by_type(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    sanitized: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        count = _sanitize_int(raw_count)
        if count is None:
            continue
        sanitized[key] = count
    return sanitized or None


def build_cycle_kpi(cycle_context: dict) -> dict:
    started_at = cycle_context.get("started_at")
    completed_at = cycle_context.get("completed_at")
    if not isinstance(started_at, datetime):
        started_at = datetime.now(UTC)
    if not isinstance(completed_at, datetime):
        completed_at = started_at

    duration_ms = _sanitize_int(cycle_context.get("duration_ms"))
    if duration_ms is None:
        duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))

    notes = cycle_context.get("notes")
    if not isinstance(notes, dict):
        notes = None

    error = cycle_context.get("error")
    error_text = str(error) if error else None

    cycle_id = cycle_context.get("cycle_id")
    if not cycle_id:
        cycle_id = started_at.isoformat()

    return {
        "cycle_id": str(cycle_id),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "requests_used_delta": _sanitize_int(cycle_context.get("requests_used_delta")),
        "requests_remaining": _sanitize_int(cycle_context.get("requests_remaining")),
        "requests_limit": _sanitize_int(cycle_context.get("requests_limit")),
        "events_processed": _sanitize_int(cycle_context.get("events_processed")),
        "snapshots_inserted": _sanitize_int(cycle_context.get("snapshots_inserted")),
        "consensus_points_written": _sanitize_int(cycle_context.get("consensus_points_written")),
        "signals_created_total": _sanitize_int(cycle_context.get("signals_created_total")),
        "signals_created_by_type": _sanitize_signals_by_type(cycle_context.get("signals_created_by_type")),
        "alerts_sent": _sanitize_int(cycle_context.get("alerts_sent")),
        "alerts_failed": _sanitize_int(cycle_context.get("alerts_failed")),
        "error": error_text,
        "degraded": bool(cycle_context.get("degraded", False)),
        "notes": notes,
        "created_at": datetime.now(UTC),
    }


async def persist_cycle_kpi(db: AsyncSession, kpi: dict) -> None:
    settings = get_settings()
    try:
        upsert_stmt = pg_insert(CycleKpi).values(**kpi)
        upsert_stmt = upsert_stmt.on_conflict_do_update(
            index_elements=["cycle_id"],
            set_={
                "started_at": upsert_stmt.excluded.started_at,
                "completed_at": upsert_stmt.excluded.completed_at,
                "duration_ms": upsert_stmt.excluded.duration_ms,
                "requests_used_delta": upsert_stmt.excluded.requests_used_delta,
                "requests_remaining": upsert_stmt.excluded.requests_remaining,
                "requests_limit": upsert_stmt.excluded.requests_limit,
                "events_processed": upsert_stmt.excluded.events_processed,
                "snapshots_inserted": upsert_stmt.excluded.snapshots_inserted,
                "consensus_points_written": upsert_stmt.excluded.consensus_points_written,
                "signals_created_total": upsert_stmt.excluded.signals_created_total,
                "signals_created_by_type": upsert_stmt.excluded.signals_created_by_type,
                "alerts_sent": upsert_stmt.excluded.alerts_sent,
                "alerts_failed": upsert_stmt.excluded.alerts_failed,
                "error": upsert_stmt.excluded.error,
                "degraded": upsert_stmt.excluded.degraded,
                "notes": upsert_stmt.excluded.notes,
            },
        )
        await db.execute(upsert_stmt)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "Failed to persist cycle KPI",
            extra={"cycle_id": str(kpi.get("cycle_id", ""))},
            exc_info=True,
        )
        if not settings.kpi_write_failures_soft:
            raise


async def cleanup_old_cycle_kpis(db: AsyncSession, retention_days: int | None = None) -> int:
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.kpi_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = delete(CycleKpi).where(CycleKpi.created_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
