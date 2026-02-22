from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


async def _fetch_scalar(db: AsyncSession, sql: str) -> Any:
    result = await db.execute(text(sql))
    return result.scalar()


async def _fetch_mappings(db: AsyncSession, sql: str) -> list[dict[str, Any]]:
    result = await db.execute(text(sql))
    return [dict(row) for row in result.mappings().all()]


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


async def run_dataset_sanity(db: AsyncSession) -> None:
    distinct_events = await _fetch_scalar(
        db,
        """
        SELECT COUNT(DISTINCT event_id) AS n
        FROM odds_snapshots;
        """,
    )

    coverage_rows = await _fetch_mappings(
        db,
        """
        SELECT
            event_id,
            MIN(fetched_at) AS first_seen,
            MAX(fetched_at) AS last_seen,
            COUNT(*) AS rows
        FROM odds_snapshots
        GROUP BY event_id
        ORDER BY last_seen DESC
        LIMIT 20;
        """,
    )

    book_rows = await _fetch_mappings(
        db,
        """
        SELECT sportsbook_key AS book, COUNT(*) AS rows
        FROM odds_snapshots
        GROUP BY sportsbook_key
        ORDER BY COUNT(*) DESC;
        """,
    )

    market_rows = await _fetch_mappings(
        db,
        """
        SELECT market, COUNT(*) AS rows
        FROM odds_snapshots
        GROUP BY market
        ORDER BY COUNT(*) DESC;
        """,
    )

    close_coverage_totals = await _fetch_mappings(
        db,
        """
        WITH event_close AS (
            SELECT
                s.event_id,
                g.commence_time,
                MAX(s.fetched_at) FILTER (
                    WHERE g.commence_time IS NOT NULL
                  AND s.fetched_at <= g.commence_time
                ) AS last_seen_before_tip
            FROM odds_snapshots
            AS s
            LEFT JOIN games AS g ON g.event_id = s.event_id
            GROUP BY s.event_id, g.commence_time
        ),
        graded AS (
            SELECT
                event_id,
                commence_time,
                last_seen_before_tip,
                EXTRACT(EPOCH FROM (commence_time - last_seen_before_tip)) / 60.0 AS minutes_to_tip,
                CASE
                    WHEN commence_time IS NULL THEN NULL
                    WHEN last_seen_before_tip IS NULL THEN 'F'
                    WHEN EXTRACT(EPOCH FROM (commence_time - last_seen_before_tip)) / 60.0 <= 10 THEN 'A'
                    WHEN EXTRACT(EPOCH FROM (commence_time - last_seen_before_tip)) / 60.0 <= 30 THEN 'B'
                    WHEN EXTRACT(EPOCH FROM (commence_time - last_seen_before_tip)) / 60.0 <= 60 THEN 'C'
                    WHEN EXTRACT(EPOCH FROM (commence_time - last_seen_before_tip)) / 60.0 <= 120 THEN 'D'
                    ELSE 'F'
                END AS close_quality
            FROM event_close
        )
        SELECT
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL) AS events_with_commence_time,
            COUNT(*) FILTER (
                WHERE commence_time IS NOT NULL
                  AND last_seen_before_tip IS NOT NULL
                  AND minutes_to_tip <= 30
                  AND minutes_to_tip >= -360
            ) AS close_covered_events,
            COUNT(*) FILTER (
                WHERE commence_time IS NOT NULL
                  AND last_seen_before_tip IS NULL
            ) AS no_pre_tip_snapshot_events,
            COUNT(*) FILTER (WHERE commence_time IS NULL) AS commence_time_unavailable_events,
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL AND close_quality = 'A') AS close_quality_a,
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL AND close_quality = 'B') AS close_quality_b,
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL AND close_quality = 'C') AS close_quality_c,
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL AND close_quality = 'D') AS close_quality_d,
            COUNT(*) FILTER (WHERE commence_time IS NOT NULL AND close_quality = 'F') AS close_quality_f
        FROM graded;
        """,
    )

    close_coverage_rows = await _fetch_mappings(
        db,
        """
        WITH event_close AS (
            SELECT
                s.event_id,
                g.commence_time,
                MAX(s.fetched_at) FILTER (
                    WHERE g.commence_time IS NOT NULL
                      AND s.fetched_at <= g.commence_time
                ) AS last_seen_before_tip,
                COUNT(*) AS rows
            FROM odds_snapshots AS s
            LEFT JOIN games AS g ON g.event_id = s.event_id
            GROUP BY s.event_id, g.commence_time
        )
        SELECT
            event_close.event_id,
            event_close.commence_time,
            event_close.last_seen_before_tip,
            ROUND(
                EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0,
                2
            ) AS minutes_to_tip,
            CASE
                WHEN event_close.commence_time IS NULL THEN 'F'
                WHEN event_close.last_seen_before_tip IS NULL THEN 'F'
                WHEN EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 <= 10
                THEN 'A'
                WHEN EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 <= 30
                THEN 'B'
                WHEN EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 <= 60
                THEN 'C'
                WHEN EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 <= 120
                THEN 'D'
                ELSE 'F'
            END AS close_quality,
            CASE
                WHEN event_close.commence_time IS NULL THEN NULL
                WHEN event_close.last_seen_before_tip IS NULL THEN FALSE
                WHEN EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 <= 30
                 AND EXTRACT(EPOCH FROM (event_close.commence_time - event_close.last_seen_before_tip)) / 60.0 >= -360
                THEN TRUE
                ELSE FALSE
            END AS close_covered,
            event_close.rows
        FROM event_close
        ORDER BY event_close.commence_time DESC NULLS LAST, event_close.event_id
        LIMIT 20;
        """,
    )

    _print_section("Dataset Sanity")
    print(f"distinct_event_count: {distinct_events}")

    _print_section("Per-Event Coverage (latest 20)")
    _print_rows(coverage_rows)

    _print_section("Book Distribution")
    _print_rows(book_rows)

    _print_section("Market Distribution")
    _print_rows(market_rows)

    coverage_summary = close_coverage_totals[0] if close_coverage_totals else {}
    events_with_commence_time = int(coverage_summary.get("events_with_commence_time") or 0)
    close_covered_events = int(coverage_summary.get("close_covered_events") or 0)
    no_pre_tip_snapshot_events = int(coverage_summary.get("no_pre_tip_snapshot_events") or 0)
    commence_time_unavailable_events = int(coverage_summary.get("commence_time_unavailable_events") or 0)
    close_quality_counts = {
        "A": int(coverage_summary.get("close_quality_a") or 0),
        "B": int(coverage_summary.get("close_quality_b") or 0),
        "C": int(coverage_summary.get("close_quality_c") or 0),
        "D": int(coverage_summary.get("close_quality_d") or 0),
        "F": int(coverage_summary.get("close_quality_f") or 0),
    }
    close_covered_pct = (
        (close_covered_events / events_with_commence_time) * 100.0
        if events_with_commence_time > 0
        else 0.0
    )

    _print_section("Close Coverage Diagnostics")
    print(f"events_with_commence_time: {events_with_commence_time}")
    print(f"close_covered_events: {close_covered_events}")
    print(f"close_covered_pct: {close_covered_pct:.2f}%")
    for grade in ("A", "B", "C", "D", "F"):
        grade_count = close_quality_counts[grade]
        grade_pct = ((grade_count / events_with_commence_time) * 100.0) if events_with_commence_time > 0 else 0.0
        print(f"close_quality_{grade}: {grade_count} ({grade_pct:.2f}%)")
    if no_pre_tip_snapshot_events > 0:
        print(f"no_pre_tip_snapshot_events: {no_pre_tip_snapshot_events}")
    if commence_time_unavailable_events > 0:
        print(
            "commence_time unavailable for "
            f"{commence_time_unavailable_events} event(s); skipping close coverage for those events."
        )

    _print_section("Close Coverage (latest 20 events)")
    _print_rows(close_coverage_rows)


async def _async_main() -> int:
    async with AsyncSessionLocal() as db:
        await run_dataset_sanity(db)
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
