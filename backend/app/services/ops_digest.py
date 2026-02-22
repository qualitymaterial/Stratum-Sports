import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ops_digest_sent import OpsDigestSent
from app.schemas.ops import OperatorReport
from app.services.operator_report import build_operator_report

logger = logging.getLogger(__name__)
settings = get_settings()


def _week_key(now_utc: datetime) -> str:
    iso = now_utc.isocalendar()
    return f"{iso.year}-{iso.week:02d}"


def should_send_ops_digest(now_utc: datetime, settings_obj: Any) -> bool:
    weekday = int(getattr(settings_obj, "ops_digest_weekday", 1))
    hour = int(getattr(settings_obj, "ops_digest_hour_utc", 13))
    minute = int(getattr(settings_obj, "ops_digest_minute_utc", 0))

    if weekday < 1 or weekday > 7:
        return False
    if now_utc.isoweekday() != weekday:
        return False
    if now_utc.hour != hour:
        return False
    return now_utc.minute >= minute


def build_ops_digest_embed(report: OperatorReport) -> dict:
    period = f"{report.period_start.isoformat()} -> {report.period_end.isoformat()}"
    avg_duration = (
        f"{report.ops.avg_cycle_duration_ms:.1f} ms"
        if report.ops.avg_cycle_duration_ms is not None
        else "n/a"
    )
    avg_remaining = (
        f"{report.ops.avg_requests_remaining:.1f}"
        if report.ops.avg_requests_remaining is not None
        else "n/a"
    )

    top_signals = sorted(
        report.ops.signals_created_by_type.items(),
        key=lambda item: (-int(item[1]), item[0]),
    )[:5]
    top_signals_text = "\n".join([f"{name}: {count}" for name, count in top_signals]) or "None"

    def _clv_rank_value(item: Any) -> float:
        values = [v for v in [item.avg_clv_line, item.avg_clv_prob] if v is not None]
        if not values:
            return float("-inf")
        return max(values)

    top_clv = sorted(
        report.performance.clv_by_signal_type,
        key=_clv_rank_value,
        reverse=True,
    )[:3]
    top_clv_text = "\n".join(
        [
            (
                f"{row.signal_type}: "
                f"line={row.avg_clv_line if row.avg_clv_line is not None else 'n/a'}, "
                f"prob={row.avg_clv_prob if row.avg_clv_prob is not None else 'n/a'}"
            )
            for row in top_clv
        ]
    ) or "None"

    return {
        "title": "STRATUM OPS WEEKLY",
        "color": 0x2F3136,
        "fields": [
            {"name": "Period", "value": period, "inline": False},
            {
                "name": "Ops",
                "value": (
                    f"Cycles: {report.ops.total_cycles}\n"
                    f"Degraded: {report.ops.degraded_cycles}\n"
                    f"Avg Duration: {avg_duration}"
                ),
                "inline": True,
            },
            {
                "name": "API",
                "value": (
                    f"Requests Used: {report.ops.total_requests_used}\n"
                    f"Remaining Avg: {avg_remaining}"
                ),
                "inline": True,
            },
            {
                "name": "Throughput",
                "value": (
                    f"Snapshots: {report.ops.total_snapshots_inserted}\n"
                    f"Consensus Points: {report.ops.total_consensus_points_written}"
                ),
                "inline": True,
            },
            {"name": "Signals (Top 5)", "value": top_signals_text, "inline": False},
            {
                "name": "Alerts",
                "value": (
                    f"Sent: {report.reliability.alerts_sent}\n"
                    f"Failed: {report.reliability.alerts_failed}\n"
                    f"Failure Rate: {report.reliability.alert_failure_rate:.4f}"
                ),
                "inline": True,
            },
            {
                "name": "Performance (Top 3 by avg CLV)",
                "value": top_clv_text,
                "inline": False,
            },
        ],
        "footer": {"text": "Internal — X-Stratum-Ops-Token protected"},
        "timestamp": report.period_end.isoformat(),
    }


async def send_ops_digest(webhook_url: str, embed: dict) -> tuple[bool, int | None]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json={"embeds": [embed]})
            return response.is_success, response.status_code
    except Exception:
        logger.exception("Failed to send ops digest webhook")
        return False, None


async def _already_sent_for_week(db: AsyncSession, redis: Redis | None, week_key: str) -> bool:
    if redis is not None:
        try:
            cached = await redis.get(f"ops:digest:last_sent:{week_key}")
            return bool(cached)
        except Exception:
            logger.exception("Ops digest redis read failed")

    stmt = select(OpsDigestSent.id).where(OpsDigestSent.week_key == week_key).limit(1)
    existing = (await db.execute(stmt)).first()
    return existing is not None


async def _mark_sent_for_week(db: AsyncSession, redis: Redis | None, week_key: str, sent_at: datetime) -> None:
    if redis is not None:
        try:
            await redis.set(f"ops:digest:last_sent:{week_key}", "1", ex=14 * 24 * 3600)
            return
        except Exception:
            logger.exception("Ops digest redis write failed")

    stmt = pg_insert(OpsDigestSent).values(week_key=week_key, sent_at=sent_at)
    stmt = stmt.on_conflict_do_nothing(index_elements=["week_key"])
    await db.execute(stmt)
    await db.commit()


async def maybe_send_weekly_ops_digest(
    db: AsyncSession,
    redis: Redis | None,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    if not settings.ops_digest_enabled:
        return {"sent": False, "reason": "disabled"}
    if not settings.ops_digest_webhook_url.strip():
        return {"sent": False, "reason": "webhook_not_configured"}

    now = now_utc or datetime.now(UTC)
    if not should_send_ops_digest(now, settings):
        return {"sent": False, "reason": "outside_schedule"}

    week_key = _week_key(now)
    if await _already_sent_for_week(db, redis, week_key):
        return {"sent": False, "reason": "already_sent"}

    report_data = await build_operator_report(db, settings.ops_digest_lookback_days)
    report = OperatorReport(**report_data)
    embed = build_ops_digest_embed(report)
    sent_ok, status_code = await send_ops_digest(settings.ops_digest_webhook_url, embed)
    if not sent_ok:
        return {"sent": False, "reason": "send_failed", "status_code": status_code}

    await _mark_sent_for_week(db, redis, week_key, now)
    return {"sent": True, "week_key": week_key, "status_code": status_code}
