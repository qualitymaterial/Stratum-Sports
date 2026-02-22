from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.odds_snapshot import OddsSnapshot
from app.services.ingestion import _upsert_game, normalize_event_odds_rows
from app.services.odds_api import HistoryProbeResult, OddsApiClient, OddsFetchResult

HistoryEndpointVariant = Literal["bulk", "event"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillConfig:
    start: datetime
    end: datetime
    sport_key: str = "basketball_nba"
    markets: tuple[str, ...] = ("spreads", "totals", "h2h")
    max_events: int = 10
    max_requests: int = 200
    min_requests_remaining: int = 50
    history_step_minutes: int = 60
    regions: str | None = None
    bookmakers: str | None = None
    probe_only: bool = False


def _parse_utc_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_markets(value: str) -> tuple[str, ...]:
    allowed = {"spreads", "totals", "h2h"}
    markets = tuple(part.strip() for part in value.split(",") if part.strip())
    if not markets:
        raise ValueError("At least one market is required")
    invalid = [market for market in markets if market not in allowed]
    if invalid:
        raise ValueError(f"Unsupported markets: {','.join(sorted(set(invalid)))}")
    return markets


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _redact_api_key(text: str, api_key: str | None) -> str:
    if not text:
        return text
    redacted = text
    if api_key:
        redacted = redacted.replace(api_key, "***REDACTED***")
    for token in ("apiKey=", "api_key="):
        if token in redacted:
            marker = redacted.split(token, 1)
            head = marker[0]
            tail = marker[1]
            if "&" in tail:
                tail = "***REDACTED***&" + tail.split("&", 1)[1]
            else:
                tail = "***REDACTED***"
            redacted = head + token + tail
    return redacted


def _within_window(value: datetime, *, start: datetime, end: datetime) -> bool:
    value_utc = value.astimezone(UTC)
    return start <= value_utc < end


def _parse_event_commence(event: dict) -> datetime | None:
    raw = event.get("commence_time")
    if not isinstance(raw, str):
        return None
    try:
        return _parse_utc_datetime(raw)
    except Exception:
        return None


def _iter_dates(start: datetime, end: datetime, step_minutes: int) -> list[datetime]:
    step = timedelta(minutes=max(1, step_minutes))
    cursor = start
    dates: list[datetime] = []
    while cursor <= end:
        dates.append(cursor)
        cursor = cursor + step
    if dates and dates[-1] < end:
        dates.append(end)
    return dates


def _tip_aware_step_minutes(
    *,
    commence_time: datetime | None,
    current_timestamp: datetime,
    default_step_minutes: int,
    event_id: str,
) -> int:
    if commence_time is None:
        logger.info(
            "[TIP-AWARE] event=%s minutes_to_tip=unavailable step=%s",
            event_id,
            default_step_minutes,
        )
        return max(1, default_step_minutes)

    minutes_to_tip = (commence_time - current_timestamp).total_seconds() / 60.0
    if minutes_to_tip > 720:
        step_minutes = 120
    elif 720 >= minutes_to_tip > 180:
        step_minutes = 60
    else:
        step_minutes = 20

    logger.info(f"[TIP-AWARE] event={event_id} minutes_to_tip={minutes_to_tip:.2f} step={step_minutes}")
    return step_minutes


def _iter_tip_aware_dates(
    *,
    event_id: str,
    commence_time: datetime | None,
    start: datetime,
    end: datetime,
    default_step_minutes: int,
) -> list[datetime]:
    if commence_time is None:
        return _iter_dates(start, end, default_step_minutes)

    cursor = start
    dates: list[datetime] = []
    while cursor <= end:
        dates.append(cursor)
        step_minutes = _tip_aware_step_minutes(
            commence_time=commence_time,
            current_timestamp=cursor,
            default_step_minutes=default_step_minutes,
            event_id=event_id,
        )
        cursor = cursor + timedelta(minutes=max(1, step_minutes))

    if dates and dates[-1] < end:
        dates.append(end)
    return dates


def _snapshot_key(row: OddsSnapshot) -> tuple[str, str, str, str, float | None, int, datetime]:
    return (
        row.event_id,
        row.sportsbook_key,
        row.market,
        row.outcome_name,
        row.line,
        row.price,
        row.fetched_at.astimezone(UTC),
    )


def _normalized_row_key(row: object) -> tuple[str, str, str, str, float | None, int, datetime]:
    # normalize_event_odds_rows returns NormalizedOddsRow dataclass from ingestion service.
    return (
        row.event_id,
        row.sportsbook_key,
        row.market,
        row.outcome_name,
        row.line,
        row.price,
        row.fetched_at.astimezone(UTC),
    )


async def _load_existing_keys(
    db: AsyncSession,
    *,
    event_id: str,
    markets: tuple[str, ...],
) -> set[tuple[str, str, str, str, float | None, int, datetime]]:
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market.in_(markets),
        )
        .order_by(OddsSnapshot.fetched_at.asc(), OddsSnapshot.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {_snapshot_key(row) for row in rows}


def _update_headers_from_response(summary: dict, result: OddsFetchResult | HistoryProbeResult) -> None:
    remaining = getattr(result, "requests_remaining", None)
    if remaining is not None:
        summary["requests_remaining"] = int(remaining)
    limit = getattr(result, "requests_limit", None)
    if limit is not None:
        summary["requests_limit"] = int(limit)


def _check_budget_stop(summary: dict, config: BackfillConfig) -> tuple[bool, str | None]:
    requests_used = int(summary["api_requests_used"])
    requests_remaining = summary.get("requests_remaining")

    if requests_used >= config.max_requests:
        logger.warning(f"[BACKFILL STOP] max_requests reached ({requests_used}).")
        return True, "max_requests_reached"
    if requests_remaining is not None and int(requests_remaining) <= config.min_requests_remaining:
        logger.warning(
            "[BACKFILL STOP] min_requests_remaining reached (%s <= %s).",
            int(requests_remaining),
            config.min_requests_remaining,
        )
        return True, "min_requests_remaining_reached"
    return False, None


def _mark_budgeted_request(summary: dict, max_requests: int) -> None:
    summary["api_requests_used"] += 1
    summary["total_http_calls"] += 1
    logger.info(
        f"[BACKFILL] request={summary['api_requests_used']}/{max_requests} "
        f"remaining_header={summary.get('requests_remaining')}"
    )


def _mark_probe_request(summary: dict) -> None:
    summary["probe_requests_used"] += 1
    summary["total_http_calls"] += 1
    logger.info(
        f"[BACKFILL][PROBE] request={summary['probe_requests_used']} "
        f"remaining_header={summary.get('requests_remaining')}"
    )


async def _probe_endpoints(
    client: OddsApiClient,
    *,
    config: BackfillConfig,
    sample_event_id: str,
    summary: dict,
) -> tuple[HistoryProbeResult, HistoryProbeResult]:
    markets_csv = ",".join(config.markets)
    _mark_probe_request(summary)
    bulk_probe = await client.probe_nba_odds_history(
        sport_key=config.sport_key,
        endpoint_variant="bulk",
        markets=markets_csv,
        regions=config.regions,
        bookmakers=config.bookmakers,
        date=config.start,
    )
    _update_headers_from_response(summary, bulk_probe)
    _mark_probe_request(summary)
    event_probe = await client.probe_nba_odds_history(
        sport_key=config.sport_key,
        endpoint_variant="event",
        event_id=sample_event_id,
        markets=markets_csv,
        regions=config.regions,
        bookmakers=config.bookmakers,
        date=config.start,
    )
    _update_headers_from_response(summary, event_probe)
    return bulk_probe, event_probe


def _choose_endpoint_variant(
    *,
    bulk_probe: HistoryProbeResult,
    event_probe: HistoryProbeResult,
) -> HistoryEndpointVariant:
    if bulk_probe.status_code < 400 and bulk_probe.events_found > 0:
        return "bulk"
    if event_probe.status_code < 400:
        return "event"
    if bulk_probe.status_code < 400:
        return "bulk"
    raise RuntimeError(
        "No working historical endpoint discovered. "
        f"bulk={bulk_probe.status_code}, event={event_probe.status_code}"
    )


def _choose_endpoint_variant_or_none(
    *,
    bulk_probe: HistoryProbeResult,
    event_probe: HistoryProbeResult,
) -> HistoryEndpointVariant | None:
    try:
        return _choose_endpoint_variant(
            bulk_probe=bulk_probe,
            event_probe=event_probe,
        )
    except RuntimeError:
        return None


def _print_probe_results(
    *,
    bulk_probe: HistoryProbeResult,
    event_probe: HistoryProbeResult,
    api_key: str | None,
) -> None:
    def _to_row(name: str, result: HistoryProbeResult) -> dict[str, object]:
        return {
            "candidate": name,
            "status_code": result.status_code,
            "events_found": result.events_found,
            "body_preview": _redact_api_key(result.body_preview, api_key)[:200],
            "requests_remaining": result.requests_remaining,
            "requests_last": result.requests_last,
            "requests_limit": result.requests_limit,
        }

    print(json.dumps(_to_row("A:/historical/sports/{sport}/odds", bulk_probe), indent=2, sort_keys=True))
    print(json.dumps(_to_row("B:/historical/sports/{sport}/events/{event}/odds", event_probe), indent=2, sort_keys=True))


async def _process_history_events(
    db: AsyncSession,
    *,
    history_events: list[dict],
    fetched_at: datetime,
    config: BackfillConfig,
    allowed_event_ids: set[str] | None,
    existing_keys_by_event: dict[str, set[tuple[str, str, str, str, float | None, int, datetime]]],
    summary: dict,
) -> None:
    allowed_markets = set(config.markets)
    for event in history_events:
        event_id = event.get("id")
        if not isinstance(event_id, str):
            continue

        if allowed_event_ids is not None and event_id not in allowed_event_ids:
            continue

        commence_time = _parse_event_commence(event)
        if commence_time is None or not _within_window(commence_time, start=config.start, end=config.end):
            continue

        await _upsert_game(db, event)
        summary["processed_event_ids"].add(event_id)

        if event_id not in existing_keys_by_event:
            existing_keys_by_event[event_id] = await _load_existing_keys(
                db,
                event_id=event_id,
                markets=config.markets,
            )
        existing_keys = existing_keys_by_event[event_id]

        normalized_rows = normalize_event_odds_rows(
            event,
            fetched_at=fetched_at,
            allowed_markets=allowed_markets,
        )
        for row in normalized_rows:
            row_key = _normalized_row_key(row)
            if row_key in existing_keys:
                summary["duplicates_skipped"] += 1
                continue

            snapshot = OddsSnapshot(
                event_id=row.event_id,
                sport_key=row.sport_key,
                commence_time=row.commence_time,
                home_team=row.home_team,
                away_team=row.away_team,
                sportsbook_key=row.sportsbook_key,
                market=row.market,
                outcome_name=row.outcome_name,
                line=row.line,
                price=row.price,
                fetched_at=row.fetched_at,
            )
            db.add(snapshot)
            existing_keys.add(row_key)
            summary["snapshots_inserted"] += 1

            current = row.fetched_at.astimezone(UTC)
            earliest = summary.get("earliest_fetched_at")
            latest = summary.get("latest_fetched_at")
            if earliest is None or current < earliest:
                summary["earliest_fetched_at"] = current
            if latest is None or current > latest:
                summary["latest_fetched_at"] = current


async def run_history_backfill(
    db: AsyncSession,
    *,
    config: BackfillConfig,
    client: OddsApiClient | None = None,
) -> dict:
    client = client or OddsApiClient()
    summary: dict = {
        "events_processed": 0,
        "api_requests_used": 0,
        "probe_requests_used": 0,
        "total_http_calls": 0,
        "requests_remaining": None,
        "requests_limit": None,
        "snapshots_inserted": 0,
        "duplicates_skipped": 0,
        "budget_stopped": False,
        "budget_stop_reason": None,
        "history_endpoint_variant": None,
        "earliest_fetched_at": None,
        "latest_fetched_at": None,
        "processed_event_ids": set(),
    }

    markets_csv = ",".join(config.markets)

    if config.probe_only:
        _mark_probe_request(summary)
    else:
        should_stop, reason = _check_budget_stop(summary, config)
        if should_stop:
            summary["budget_stopped"] = True
            summary["budget_stop_reason"] = reason
            summary["events_processed"] = 0
            summary["earliest_fetched_at"] = None
            summary["latest_fetched_at"] = None
            summary.pop("processed_event_ids", None)
            return summary
        _mark_budgeted_request(summary, config.max_requests)

    events_fetch = await client.fetch_nba_odds(
        sport_key=config.sport_key,
        markets=markets_csv,
        regions=config.regions,
        bookmakers=config.bookmakers,
    )
    _update_headers_from_response(summary, events_fetch)

    if not config.probe_only:
        should_stop, reason = _check_budget_stop(summary, config)
        if should_stop:
            summary["budget_stopped"] = True
            summary["budget_stop_reason"] = reason
            summary["events_processed"] = 0
            summary["earliest_fetched_at"] = None
            summary["latest_fetched_at"] = None
            summary.pop("processed_event_ids", None)
            return summary

    candidate_events = []
    for event in events_fetch.events:
        commence_time = _parse_event_commence(event)
        event_id = event.get("id")
        if commence_time is None or not isinstance(event_id, str):
            continue
        if _within_window(commence_time, start=config.start, end=config.end):
            candidate_events.append(event)

    logger.info(f"[BACKFILL] candidate_events={len(candidate_events)}")

    candidate_events.sort(key=lambda event: (event.get("commence_time", ""), event.get("id", "")))
    selected_events = candidate_events[: max(0, config.max_events)]
    logger.info(
        "[BACKFILL] selected_events=%s max_events=%s probe_only=%s",
        len(selected_events),
        config.max_events,
        config.probe_only,
    )
    sample_event_id = selected_events[0]["id"] if selected_events else None

    if not sample_event_id:
        if config.probe_only:
            print("No candidate events found in the requested window; probe skipped.")
        summary["events_processed"] = 0
        summary["earliest_fetched_at"] = None
        summary["latest_fetched_at"] = None
        summary.pop("processed_event_ids", None)
        return summary

    bulk_probe, event_probe = await _probe_endpoints(
        client,
        config=config,
        sample_event_id=sample_event_id,
        summary=summary,
    )

    if config.probe_only:
        api_key = get_settings().odds_api_key
        _print_probe_results(
            bulk_probe=bulk_probe,
            event_probe=event_probe,
            api_key=api_key,
        )
        summary["history_endpoint_variant"] = _choose_endpoint_variant_or_none(
            bulk_probe=bulk_probe,
            event_probe=event_probe,
        )
        summary["events_processed"] = 0
        summary["earliest_fetched_at"] = None
        summary["latest_fetched_at"] = None
        summary.pop("processed_event_ids", None)
        return summary

    endpoint_variant = _choose_endpoint_variant(bulk_probe=bulk_probe, event_probe=event_probe)
    summary["history_endpoint_variant"] = endpoint_variant

    should_stop, reason = _check_budget_stop(summary, config)
    if should_stop:
        summary["budget_stopped"] = True
        summary["budget_stop_reason"] = reason
        summary["events_processed"] = 0
        summary["earliest_fetched_at"] = None
        summary["latest_fetched_at"] = None
        summary.pop("processed_event_ids", None)
        return summary

    existing_keys_by_event: dict[str, set[tuple[str, str, str, str, float | None, int, datetime]]] = {}
    allowed_event_ids = {event["id"] for event in selected_events}

    try:
        if endpoint_variant == "bulk":
            bulk_dates: set[datetime] = set()
            for event in selected_events:
                event_id = str(event["id"])
                commence_time = _parse_event_commence(event)
                event_dates = _iter_tip_aware_dates(
                    event_id=event_id,
                    commence_time=commence_time,
                    start=config.start,
                    end=config.end,
                    default_step_minutes=config.history_step_minutes,
                )
                bulk_dates.update(event_dates)

            history_dates = sorted(bulk_dates)
            for date in history_dates:
                should_stop, reason = _check_budget_stop(summary, config)
                if should_stop:
                    summary["budget_stopped"] = True
                    summary["budget_stop_reason"] = reason
                    break
                _mark_budgeted_request(summary, config.max_requests)

                result = await client.fetch_nba_odds_history(
                    sport_key=config.sport_key,
                    endpoint_variant="bulk",
                    markets=markets_csv,
                    regions=config.regions,
                    bookmakers=config.bookmakers,
                    date=date,
                )
                _update_headers_from_response(summary, result)
                history_fetched_at = result.history_timestamp or date
                await _process_history_events(
                    db,
                    history_events=result.events,
                    fetched_at=history_fetched_at,
                    config=config,
                    allowed_event_ids=allowed_event_ids,
                    existing_keys_by_event=existing_keys_by_event,
                    summary=summary,
                )
        else:
            for event in selected_events:
                event_id = event["id"]
                commence_time = _parse_event_commence(event)
                history_dates = _iter_tip_aware_dates(
                    event_id=event_id,
                    commence_time=commence_time,
                    start=config.start,
                    end=config.end,
                    default_step_minutes=config.history_step_minutes,
                )
                for date in history_dates:
                    should_stop, reason = _check_budget_stop(summary, config)
                    if should_stop:
                        summary["budget_stopped"] = True
                        summary["budget_stop_reason"] = reason
                        break
                    _mark_budgeted_request(summary, config.max_requests)

                    result = await client.fetch_nba_odds_history(
                        sport_key=config.sport_key,
                        endpoint_variant="event",
                        event_id=event_id,
                        markets=markets_csv,
                        regions=config.regions,
                        bookmakers=config.bookmakers,
                        date=date,
                    )
                    _update_headers_from_response(summary, result)
                    history_fetched_at = result.history_timestamp or date
                    await _process_history_events(
                        db,
                        history_events=result.events,
                        fetched_at=history_fetched_at,
                        config=config,
                        allowed_event_ids=allowed_event_ids,
                        existing_keys_by_event=existing_keys_by_event,
                        summary=summary,
                    )

                if summary["budget_stopped"]:
                    break
    finally:
        await db.commit()

    summary["events_processed"] = len(summary["processed_event_ids"])
    if len(candidate_events) >= config.max_events and summary["events_processed"] < config.max_events:
        logger.warning(
            "[BACKFILL WARN] Processed fewer events than max_events despite sufficient candidates "
            "— check filtering/early-stop."
        )
    summary["earliest_fetched_at"] = (
        summary["earliest_fetched_at"].isoformat() if summary["earliest_fetched_at"] is not None else None
    )
    summary["latest_fetched_at"] = (
        summary["latest_fetched_at"].isoformat() if summary["latest_fetched_at"] is not None else None
    )
    summary.pop("processed_event_ids", None)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-off historical Odds API backfill")
    parser.add_argument("--start", required=True, help="UTC start datetime (ISO8601, e.g. 2026-02-18T00:00:00Z)")
    parser.add_argument("--end", required=True, help="UTC end datetime (ISO8601, e.g. 2026-02-22T00:00:00Z)")
    parser.add_argument("--sport_key", default="basketball_nba", help="Sport key")
    parser.add_argument("--markets", default="spreads,totals,h2h", help="Comma-separated markets")
    parser.add_argument("--max_events", type=int, default=10, help="Maximum events to process")
    parser.add_argument("--max_requests", type=int, default=200, help="Hard cap for API requests")
    parser.add_argument(
        "--min_requests_remaining",
        type=int,
        default=50,
        help="Stop if requests remaining is at or below this threshold",
    )
    parser.add_argument("--history_step_minutes", type=int, default=60, help="Historical snapshot interval")
    parser.add_argument("--regions", default=None, help="Override regions query param")
    parser.add_argument("--bookmakers", default=None, help="Override bookmakers query param")
    parser.add_argument(
        "--probe_only",
        type=_parse_bool,
        default=False,
        help="Probe historical endpoint variants only and exit",
    )
    return parser


async def _async_main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    config = BackfillConfig(
        start=_parse_utc_datetime(str(args.start)),
        end=_parse_utc_datetime(str(args.end)),
        sport_key=str(args.sport_key),
        markets=_parse_markets(str(args.markets)),
        max_events=max(0, int(args.max_events)),
        max_requests=max(1, int(args.max_requests)),
        min_requests_remaining=max(0, int(args.min_requests_remaining)),
        history_step_minutes=max(1, int(args.history_step_minutes)),
        regions=(str(args.regions).strip() if args.regions else None),
        bookmakers=(str(args.bookmakers).strip() if args.bookmakers else None),
        probe_only=bool(args.probe_only),
    )

    async with AsyncSessionLocal() as db:
        summary = await run_history_backfill(db, config=config)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
