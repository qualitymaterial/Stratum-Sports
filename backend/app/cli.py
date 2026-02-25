from __future__ import annotations

import argparse
import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.tools.backfill_time_bucket import run_time_bucket_backfill


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stratum operational CLI")
    subparsers = parser.add_subparsers(dest="command")

    backfill_parser = subparsers.add_parser(
        "backfill_time_bucket",
        help="Backfill signal time_bucket values from stored minutes_to_tip metadata",
    )
    backfill_parser.add_argument("--days", type=int, default=30, help="Only scan signals from last N days")
    backfill_parser.add_argument("--chunk-size", type=int, default=500, help="Rows per batch")

    return parser


async def _run_backfill_time_bucket(days: int, chunk_size: int) -> int:
    async with AsyncSessionLocal() as db:
        summary = await run_time_bucket_backfill(
            db,
            days=max(1, int(days)),
            chunk_size=max(1, int(chunk_size)),
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    if args.command == "backfill_time_bucket":
        return asyncio.run(_run_backfill_time_bucket(args.days, args.chunk_size))

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

