from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.signal import Signal
from app.services.time_bucket import compute_time_bucket

logger = logging.getLogger(__name__)


def _coerce_minutes(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def run_time_bucket_backfill(
    db: AsyncSession,
    *,
    days: int = 30,
    chunk_size: int = 500,
) -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(days=max(1, int(days)))
    limit = max(1, int(chunk_size))
    scanned = 0
    updated = 0
    batches = 0

    while True:
        stmt = (
            select(Signal)
            .where(
                Signal.created_at >= cutoff,
                or_(Signal.time_bucket.is_(None), Signal.time_bucket == "UNKNOWN"),
            )
            .order_by(Signal.created_at.asc(), Signal.id.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            break

        for signal in rows:
            scanned += 1
            metadata = signal.metadata_json or {}
            minutes_to_tip = _coerce_minutes(metadata.get("minutes_to_tip"))
            bucket = compute_time_bucket(minutes_to_tip)
            if signal.time_bucket != bucket:
                signal.time_bucket = bucket
                updated += 1

        await db.commit()
        batches += 1

    return {
        "days": max(1, int(days)),
        "chunk_size": limit,
        "cutoff_utc": cutoff.isoformat(),
        "rows_scanned": scanned,
        "rows_updated": updated,
        "batches": batches,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill signal time_bucket from stored minutes_to_tip metadata")
    parser.add_argument("--days", type=int, default=30, help="Only scan signals created in the last N days")
    parser.add_argument("--chunk-size", type=int, default=500, help="Rows per batch commit")
    return parser


async def _async_main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    async with AsyncSessionLocal() as db:
        summary = await run_time_bucket_backfill(
            db,
            days=max(1, int(args.days)),
            chunk_size=max(1, int(args.chunk_size)),
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())

