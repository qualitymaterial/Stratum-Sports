from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


@dataclass
class EventRow:
    event_id: str
    home_team: str
    away_team: str
    start_time: datetime | None
    status: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print actionable live board from Stratum DB data.")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--limit-events", type=int, default=10)
    parser.add_argument("--limit-signals", type=int, default=5)
    parser.add_argument("--min-confidence", type=int, default=60)
    parser.add_argument("--event-id", type=str, default=None)
    parser.add_argument(
        "--signal-types",
        type=str,
        default="MOVE,KEY_CROSS,MULTIBOOK_SYNC",
        help="Comma-separated signal types",
    )
    return parser.parse_args()


def _print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(no rows)")
        return

    columns = list(rows[0].keys())
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col))))

    header = " | ".join(col.ljust(widths[col]) for col in columns)
    divider = "-+-".join("-" * widths[col] for col in columns)
    print(header)
    print(divider)
    for row in rows:
        print(" | ".join(str(row.get(col)).ljust(widths[col]) for col in columns))


def _format_ts(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    if value is None:
        return "-"
    return str(value)


def _format_num(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _parse_signal_types(raw: str) -> list[str]:
    values = [v.strip() for v in raw.split(",") if v.strip()]
    return values or ["MOVE", "KEY_CROSS", "MULTIBOOK_SYNC"]


def _derive_status(start_time: datetime | None, now_utc: datetime) -> str:
    if start_time is None:
        return "unknown"
    if now_utc < start_time:
        return "pre"
    if now_utc <= start_time + timedelta(hours=4):
        return "live"
    return "post"


def _choose_first(columns: set[str], candidates: list[str]) -> str | None:
    for col in candidates:
        if col in columns:
            return col
    return None


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table_name}"})
    return result.scalar() is not None


async def _table_columns(db: AsyncSession, table_name: str) -> set[str]:
    if not await _table_exists(db, table_name):
        return set()
    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0] for row in result.all()}


async def _fetch_mappings(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def _load_events(
    db: AsyncSession,
    *,
    limit_events: int,
    event_id: str | None,
    now_utc: datetime,
) -> list[EventRow]:
    columns = await _table_columns(db, "games")
    if not columns:
        _print_section("EVENTS")
        print("Table not found")
        return []

    id_col = _choose_first(columns, ["event_id", "id"]) or "event_id"
    home_col = _choose_first(columns, ["home_team", "home", "team_home"]) or "'-'"
    away_col = _choose_first(columns, ["away_team", "away", "team_away"]) or "'-'"
    start_col = _choose_first(columns, ["commence_time", "start_time", "scheduled_at", "created_at"])
    status_col = _choose_first(columns, ["status", "game_status"])

    start_expr = f"{start_col}" if start_col else "NULL"
    status_expr = f"{status_col}" if status_col else "NULL"

    params: dict[str, Any] = {"limit_events": max(1, limit_events)}
    where_clauses: list[str] = []
    if event_id:
        where_clauses.append(f"{id_col} = :event_id")
        params["event_id"] = event_id
    elif start_col:
        where_clauses.append(f"{start_col} >= :window_start")
        where_clauses.append(f"{start_col} <= :window_end")
        params["window_start"] = now_utc - timedelta(hours=6)
        params["window_end"] = now_utc + timedelta(hours=12)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    order_sql = f"ORDER BY {start_col} ASC NULLS LAST" if start_col else "ORDER BY id DESC"
    rows = await _fetch_mappings(
        db,
        f"""
        SELECT
            {id_col}::text AS event_id,
            {home_col}::text AS home_team,
            {away_col}::text AS away_team,
            {start_expr} AS start_time,
            {status_expr}::text AS status
        FROM games
        {where_sql}
        {order_sql}
        LIMIT :limit_events
        """,
        params,
    )

    events: list[EventRow] = []
    for row in rows:
        events.append(
            EventRow(
                event_id=str(row.get("event_id") or ""),
                home_team=str(row.get("home_team") or "-"),
                away_team=str(row.get("away_team") or "-"),
                start_time=row.get("start_time"),
                status=str(row.get("status")) if row.get("status") not in (None, "") else None,
            )
        )
    return events


def _signal_type_filter_sql(signal_type_col: str, signal_types: list[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if not signal_types:
        return "", params
    placeholders: list[str] = []
    for idx, value in enumerate(signal_types):
        key = f"stype_{idx}"
        placeholders.append(f":{key}")
        params[key] = value
    return f"AND {signal_type_col} IN ({', '.join(placeholders)})", params


async def _load_signals_for_event(
    db: AsyncSession,
    *,
    event_id: str,
    cutoff: datetime,
    limit_signals: int,
    min_confidence: int,
    signal_types: list[str],
) -> list[dict[str, Any]]:
    columns = await _table_columns(db, "signals")
    if not columns:
        return []

    event_col = _choose_first(columns, ["event_id"])
    type_col = _choose_first(columns, ["signal_type", "type"])
    market_col = _choose_first(columns, ["market"])
    created_col = _choose_first(columns, ["created_at", "updated_at", "fetched_at", "timestamp"])
    confidence_col = _choose_first(columns, ["confidence", "strength_score"])

    if event_col is None or type_col is None:
        return []

    confidence_expr = confidence_col if confidence_col else "NULL"
    min_conf_filter = f"AND {confidence_col} >= :min_confidence" if confidence_col else ""
    market_expr = market_col if market_col else "NULL"
    created_filter = f"AND {created_col} >= :cutoff" if created_col else ""
    created_expr = created_col if created_col else "NULL"
    order_col = created_col if created_col else "id"
    type_sql, type_params = _signal_type_filter_sql(type_col, signal_types)

    params: dict[str, Any] = {
        "event_id": event_id,
        "limit_signals": max(1, limit_signals),
        "min_confidence": min_confidence,
        **type_params,
    }
    if created_col:
        params["cutoff"] = cutoff

    return await _fetch_mappings(
        db,
        f"""
        SELECT
            {type_col}::text AS signal_type,
            {confidence_expr} AS confidence,
            {market_expr}::text AS market,
            {created_expr} AS created_at
        FROM signals
        WHERE {event_col} = :event_id
          {created_filter}
          {min_conf_filter}
          {type_sql}
        ORDER BY {order_col} DESC NULLS LAST
        LIMIT :limit_signals
        """,
        params,
    )


async def _load_latest_odds_for_market(
    db: AsyncSession,
    *,
    event_id: str,
    market: str,
) -> list[dict[str, Any]]:
    columns = await _table_columns(db, "odds_snapshots")
    if not columns:
        return []

    event_col = _choose_first(columns, ["event_id"])
    market_col = _choose_first(columns, ["market"])
    book_col = _choose_first(columns, ["sportsbook_key", "book", "bookmaker_key"])
    outcome_col = _choose_first(columns, ["outcome_name", "outcome", "selection"])
    price_col = _choose_first(columns, ["price", "odds"])
    line_col = _choose_first(columns, ["line", "point", "handicap", "spread", "total"])
    time_col = _choose_first(columns, ["fetched_at", "created_at", "updated_at", "timestamp"])

    if event_col is None or market_col is None or book_col is None or price_col is None or time_col is None:
        return []

    outcome_expr = outcome_col if outcome_col else "NULL"
    line_expr = line_col if line_col else "NULL"
    partition_cols = [book_col]
    if outcome_col:
        partition_cols.append(outcome_col)
    partition_sql = ", ".join(partition_cols)

    return await _fetch_mappings(
        db,
        f"""
        SELECT
            book::text AS book,
            market::text AS market,
            outcome_name::text AS outcome_name,
            price,
            line,
            updated_at
        FROM (
            SELECT
                {book_col} AS book,
                {market_col} AS market,
                {outcome_expr} AS outcome_name,
                {price_col} AS price,
                {line_expr} AS line,
                {time_col} AS updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY {partition_sql}
                    ORDER BY {time_col} DESC NULLS LAST
                ) AS rn
            FROM odds_snapshots
            WHERE {event_col} = :event_id
              AND {market_col} = :market
        ) ranked
        WHERE rn = 1
        ORDER BY book ASC, outcome_name ASC
        """,
        {"event_id": event_id, "market": market},
    )


def _format_market_board(odds_rows: list[dict[str, Any]]) -> tuple[str, str]:
    if not odds_rows:
        return "no odds found", "-"

    by_book: dict[str, list[dict[str, Any]]] = defaultdict(list)
    last_updated: datetime | None = None
    for row in odds_rows:
        book = str(row.get("book") or "unknown")
        by_book[book].append(row)
        updated_at = row.get("updated_at")
        if isinstance(updated_at, datetime):
            if last_updated is None or updated_at > last_updated:
                last_updated = updated_at

    segments: list[str] = []
    for book in sorted(by_book.keys()):
        outcomes: list[str] = []
        for row in sorted(by_book[book], key=lambda r: str(r.get("outcome_name") or "")):
            outcome = str(row.get("outcome_name") or "").strip()
            price = _format_num(row.get("price"))
            line = row.get("line")
            if line is not None:
                line_text = _format_num(line)
                if outcome:
                    outcomes.append(f"{outcome} {line_text} ({price})")
                else:
                    outcomes.append(f"{line_text} ({price})")
            else:
                if outcome:
                    outcomes.append(f"{outcome} {price}")
                else:
                    outcomes.append(price)
        segments.append(f"{book}: {', '.join(outcomes) if outcomes else '-'}")

    max_books_to_print = 5
    if len(segments) > max_books_to_print:
        shown = segments[:max_books_to_print]
        shown.append(f"... +{len(segments) - max_books_to_print} more books")
        segments = shown

    return "; ".join(segments), _format_ts(last_updated)


async def run_actionable_live_board(args: argparse.Namespace) -> None:
    minutes = max(1, int(args.minutes))
    limit_events = max(1, int(args.limit_events))
    limit_signals = max(1, int(args.limit_signals))
    min_confidence = max(0, int(args.min_confidence))
    signal_types = _parse_signal_types(args.signal_types)

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(minutes=minutes)

    async with AsyncSessionLocal() as db:
        events = await _load_events(
            db,
            limit_events=limit_events,
            event_id=args.event_id,
            now_utc=now_utc,
        )

        _print_section("ACTIONABLE LIVE BOARD")
        print(f"generated_at_utc: {_format_ts(now_utc)}")
        print(f"signal_window_minutes: {minutes}")
        print(f"signal_cutoff_utc: {_format_ts(cutoff)}")
        print(f"signal_types: {','.join(signal_types)}")
        print(f"min_confidence: {min_confidence}")
        print(f"events_returned: {len(events)}")

        if not events:
            return

        odds_cache: dict[tuple[str, str], tuple[str, str]] = {}

        for idx, event in enumerate(events, start=1):
            raw_status = (event.status or "").strip().lower()
            status = raw_status if raw_status else _derive_status(event.start_time, now_utc)

            _print_section(
                f"EVENT {idx}: {event.home_team} vs {event.away_team} | "
                f"start={_format_ts(event.start_time)} | status={status} | event_id={event.event_id}"
            )

            signals = await _load_signals_for_event(
                db,
                event_id=event.event_id,
                cutoff=cutoff,
                limit_signals=limit_signals,
                min_confidence=min_confidence,
                signal_types=signal_types,
            )
            if not signals:
                print("No qualifying signals in window.")
                continue

            rows: list[dict[str, Any]] = []
            for signal in signals:
                signal_market = (signal.get("market") or "").strip().lower()
                markets = [signal_market] if signal_market else ["h2h", "spreads", "totals"]

                best_parts: list[str] = []
                latest_timestamps: list[str] = []
                for market in markets:
                    cache_key = (event.event_id, market)
                    cached = odds_cache.get(cache_key)
                    if cached is None:
                        odds_rows = await _load_latest_odds_for_market(db, event_id=event.event_id, market=market)
                        cached = _format_market_board(odds_rows)
                        odds_cache[cache_key] = cached
                    board_text, updated_at_text = cached
                    best_parts.append(f"{market}: {board_text}")
                    if updated_at_text != "-":
                        latest_timestamps.append(updated_at_text)

                last_updated_text = max(latest_timestamps) if latest_timestamps else "-"
                rows.append(
                    {
                        "signal_type": signal.get("signal_type") or "-",
                        "confidence": _format_num(signal.get("confidence")),
                        "market": signal_market or "multi",
                        "best_current": " | ".join(best_parts),
                        "last_updated": last_updated_text,
                    }
                )

            _print_rows(rows)


async def _async_main() -> int:
    args = _parse_args()
    await run_actionable_live_board(args)
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
