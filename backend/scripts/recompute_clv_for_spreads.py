import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from sqlalchemy import select

# Ensure `app` imports resolve when script is executed as `python scripts/...`.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.models.clv_record import ClvRecord


def _compute_spread_clv_line(entry_line: float, close_line: float) -> float:
    # Spread CLV must be side-normalized by entry side:
    # - favorites (entry < 0): entry - close
    # - underdogs (entry > 0): close - entry
    # - pick'em (entry == 0): close - entry
    if entry_line < 0:
        return entry_line - close_line
    return close_line - entry_line


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "mean": None}
    return {
        "min": min(values),
        "median": median(values),
        "mean": sum(values) / len(values),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute spread CLV line values using side-normalized spread logic.",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Optional inclusive UTC date filter on ClvRecord.computed_at (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing updates.",
    )
    args = parser.parse_args()

    since_dt: datetime | None = None
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise SystemExit(f"Invalid --since value '{args.since}'. Expected YYYY-MM-DD.") from exc

    async with AsyncSessionLocal() as db:
        stmt = select(ClvRecord).where(
            ClvRecord.market == "spreads",
            ClvRecord.entry_line.is_not(None),
            ClvRecord.close_line.is_not(None),
        )
        if since_dt is not None:
            stmt = stmt.where(ClvRecord.computed_at >= since_dt)
        stmt = stmt.order_by(ClvRecord.computed_at.asc())

        rows = (await db.execute(stmt)).scalars().all()

        scanned = len(rows)
        changed = 0
        before_values: list[float] = []
        after_values: list[float] = []

        for row in rows:
            entry_line = float(row.entry_line)  # guarded by query filter
            close_line = float(row.close_line)  # guarded by query filter
            new_line = _compute_spread_clv_line(entry_line, close_line)
            old_line = float(row.clv_line) if row.clv_line is not None else None

            if old_line is None or abs(old_line - new_line) > 1e-12:
                changed += 1
                before_values.append(old_line if old_line is not None else 0.0)
                after_values.append(new_line)
                if not args.dry_run:
                    row.clv_line = new_line

        if not args.dry_run and changed > 0:
            await db.commit()

    before_summary = _summary(before_values)
    after_summary = _summary(after_values)
    mode = "DRY-RUN" if args.dry_run else "UPDATED"

    print(f"[{mode}] spreads scanned: {scanned}")
    print(f"[{mode}] rows changed: {changed}")
    if since_dt is not None:
        print(f"[{mode}] since: {since_dt.date().isoformat()}")
    print(
        f"[{mode}] before clv_line summary (changed rows): "
        f"min={before_summary['min']} median={before_summary['median']} mean={before_summary['mean']}"
    )
    print(
        f"[{mode}] after  clv_line summary (changed rows): "
        f"min={after_summary['min']} median={after_summary['median']} mean={after_summary['mean']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
