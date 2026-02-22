from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


def _print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(no rows)")
        return

    columns = list(rows[0].keys())
    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = max(widths[column], len(str(row.get(column))))

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    divider = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(divider)
    for row in rows:
        print(" | ".join(str(row.get(column)).ljust(widths[column]) for column in columns))


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"})
    return result.scalar() is not None


async def _column_exists(db: AsyncSession, table_name: str, column_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar())


async def _fetch_count(db: AsyncSession, table_name: str) -> int:
    result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return int(result.scalar() or 0)


async def _fetch_rows(db: AsyncSession, sql: str) -> list[dict[str, Any]]:
    result = await db.execute(text(sql))
    return [dict(row) for row in result.mappings().all()]


async def run_live_data_snapshot(db: AsyncSession) -> None:
    _print_section("=== TABLE ROW COUNTS ===")
    count_tables = [
        ("odds", "odds_snapshots"),
        ("events", "games"),
        ("signals", "signals"),
        ("consensus_points", "market_consensus_snapshots"),
    ]
    for label, table_name in count_tables:
        if not await _table_exists(db, table_name):
            print(f"{label}: Table not found")
            continue
        print(f"{label}: {await _fetch_count(db, table_name)}")

    _print_section("=== LATEST EVENTS (10) ===")
    if not await _table_exists(db, "games"):
        print("Table not found")
    else:
        status_expr = "status" if await _column_exists(db, "games", "status") else "'unknown'"
        order_col = "created_at" if await _column_exists(db, "games", "created_at") else "commence_time"
        event_id_expr = "event_id" if await _column_exists(db, "games", "event_id") else "id::text"
        rows = await _fetch_rows(
            db,
            f"""
            SELECT
                {event_id_expr} AS id,
                home_team,
                away_team,
                commence_time AS start_time,
                {status_expr} AS status
            FROM games
            ORDER BY {order_col} DESC NULLS LAST
            LIMIT 10
            """,
        )
        _print_rows(rows)

    _print_section("=== LATEST ODDS (20) ===")
    if not await _table_exists(db, "odds_snapshots"):
        print("Table not found")
    else:
        book_expr = (
            "sportsbook_key"
            if await _column_exists(db, "odds_snapshots", "sportsbook_key")
            else ("book" if await _column_exists(db, "odds_snapshots", "book") else "'unknown'")
        )
        if await _column_exists(db, "odds_snapshots", "created_at"):
            odds_time_col = "created_at"
        elif await _column_exists(db, "odds_snapshots", "fetched_at"):
            odds_time_col = "fetched_at"
        else:
            odds_time_col = "commence_time"

        rows = await _fetch_rows(
            db,
            f"""
            SELECT
                event_id,
                {book_expr} AS book,
                market,
                price,
                {odds_time_col} AS created_at
            FROM odds_snapshots
            ORDER BY {odds_time_col} DESC NULLS LAST
            LIMIT 20
            """,
        )
        _print_rows(rows)

    _print_section("=== LATEST SIGNALS (20) ===")
    if not await _table_exists(db, "signals"):
        print("Table not found")
    else:
        if await _column_exists(db, "signals", "confidence"):
            confidence_expr = "confidence"
        elif await _column_exists(db, "signals", "strength_score"):
            confidence_expr = "strength_score"
        else:
            confidence_expr = "NULL"
        signal_time_col = "created_at" if await _column_exists(db, "signals", "created_at") else "id"
        rows = await _fetch_rows(
            db,
            f"""
            SELECT
                event_id,
                signal_type,
                {signal_time_col} AS created_at,
                {confidence_expr} AS confidence
            FROM signals
            ORDER BY {signal_time_col} DESC NULLS LAST
            LIMIT 20
            """,
        )
        _print_rows(rows)


async def _async_main() -> int:
    async with AsyncSessionLocal() as db:
        await run_live_data_snapshot(db)
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
