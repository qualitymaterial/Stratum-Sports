import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.consensus import compute_and_persist_consensus
from app.services.odds_api import OddsApiClient, OddsFetchResult
from app.services.quote_moves import detect_quote_moves

logger = logging.getLogger(__name__)

REDIS_DEDUPE_UPDATE_IF_CHANGED_LUA = """
local existing = redis.call("GET", KEYS[1])
if existing == ARGV[1] then
    return 0
end
redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[2])
return 1
"""


@dataclass(frozen=True)
class NormalizedOddsRow:
    event_id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    sportsbook_key: str
    market: str
    outcome_name: str
    line: float | None
    price: int
    fetched_at: datetime


async def cleanup_old_snapshots(db: AsyncSession, hours_to_keep: int | None = None) -> int:
    """Delete odds snapshots older than the configured retention period."""
    hours = hours_to_keep if hours_to_keep is not None else get_settings().snapshot_retention_hours
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = delete(OddsSnapshot).where(OddsSnapshot.fetched_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


async def cleanup_old_signals(db: AsyncSession, days_to_keep: int | None = None) -> int:
    """Delete signals older than the configured retention period."""
    days = days_to_keep if days_to_keep is not None else get_settings().signal_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = delete(Signal).where(Signal.created_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_line(market: str, outcome: dict) -> float | None:
    if market in {"spreads", "totals"}:
        point = outcome.get("point")
        return float(point) if point is not None else None
    return None


async def _upsert_game(db: AsyncSession, event: dict) -> Game:
    event_id = event["id"]
    stmt = select(Game).where(Game.event_id == event_id)
    game = (await db.execute(stmt)).scalar_one_or_none()

    commence_time = _parse_iso_datetime(event["commence_time"])
    if game is None:
        game = Game(
            event_id=event_id,
            sport_key=event.get("sport_key", "basketball_nba"),
            commence_time=commence_time,
            home_team=event["home_team"],
            away_team=event["away_team"],
        )
        db.add(game)
        return game

    game.sport_key = event.get("sport_key", "basketball_nba")
    game.commence_time = commence_time
    game.home_team = event["home_team"]
    game.away_team = event["away_team"]
    return game


def normalize_event_odds_rows(
    event: dict,
    *,
    fetched_at: datetime,
    allowed_markets: set[str] | None = None,
) -> list[NormalizedOddsRow]:
    if allowed_markets is None:
        allowed_markets = {"spreads", "totals", "h2h"}

    event_id = event["id"]
    sport_key = event.get("sport_key", "basketball_nba")
    commence_time = _parse_iso_datetime(event["commence_time"])
    home_team = event["home_team"]
    away_team = event["away_team"]

    rows: list[NormalizedOddsRow] = []
    bookmakers = event.get("bookmakers", [])
    for bookmaker in bookmakers:
        sportsbook_key = bookmaker.get("key")
        if not sportsbook_key:
            continue

        for market_entry in bookmaker.get("markets", []):
            market = market_entry.get("key")
            if market not in allowed_markets:
                continue

            for outcome in market_entry.get("outcomes", []):
                outcome_name = outcome.get("name")
                price = outcome.get("price")
                if outcome_name is None or price is None:
                    continue

                rows.append(
                    NormalizedOddsRow(
                        event_id=event_id,
                        sport_key=sport_key,
                        commence_time=commence_time,
                        home_team=home_team,
                        away_team=away_team,
                        sportsbook_key=sportsbook_key,
                        market=market,
                        outcome_name=str(outcome_name),
                        line=_normalize_line(market, outcome),
                        price=int(price),
                        fetched_at=fetched_at,
                    )
                )

    return rows


async def _should_persist_snapshot(
    redis: Redis | None,
    *,
    dedupe_key: str,
    dedupe_value: str,
    ttl_seconds: int = 60 * 60 * 24,
) -> bool:
    if redis is None:
        return True
    try:
        changed = await redis.eval(
            REDIS_DEDUPE_UPDATE_IF_CHANGED_LUA,
            1,
            dedupe_key,
            dedupe_value,
            str(ttl_seconds),
        )
        return bool(changed)
    except Exception:
        logger.exception("Redis dedupe failed; continuing without dedupe")
        return True


async def ingest_odds_cycle(
    db: AsyncSession,
    redis: Redis | None,
    eligible_event_ids: set[str] | None = None,
) -> dict:
    settings = get_settings()
    client = OddsApiClient()
    sport_keys = settings.odds_api_sport_keys_list
    fetch_results: list[tuple[str, OddsFetchResult]] = []
    for sport_key in sport_keys:
        fetch_results.append((sport_key, await client.fetch_nba_odds(sport_key=sport_key)))

    events: list[dict] = []
    requests_remaining_values: list[int] = []
    requests_used_values: list[int] = []
    requests_limit_values: list[int] = []
    requests_last_total = 0
    requests_last_seen = False
    per_sport_events_seen: dict[str, int] = {}

    for sport_key, fetch_result in fetch_results:
        sport_events = fetch_result.events if isinstance(fetch_result.events, list) else []
        per_sport_events_seen[sport_key] = len(sport_events)
        events.extend(sport_events)
        if fetch_result.requests_remaining is not None:
            requests_remaining_values.append(fetch_result.requests_remaining)
        if fetch_result.requests_used is not None:
            requests_used_values.append(fetch_result.requests_used)
        if fetch_result.requests_limit is not None:
            requests_limit_values.append(fetch_result.requests_limit)
        if fetch_result.requests_last is not None:
            requests_last_total += fetch_result.requests_last
            requests_last_seen = True

    api_requests_remaining = min(requests_remaining_values) if requests_remaining_values else None
    api_requests_used = max(requests_used_values) if requests_used_values else None
    api_requests_limit = max(requests_limit_values) if requests_limit_values else None
    api_requests_last = requests_last_total if requests_last_seen else None

    if eligible_event_ids is not None:
        events = [
            event
            for event in events
            if isinstance(event, dict) and isinstance(event.get("id"), str) and event["id"] in eligible_event_ids
        ]
        logger.info(
            "Close-capture event filter applied",
            extra={
                "eligible_event_ids": len(eligible_event_ids),
                "events_selected": len(events),
            },
        )
    if not events:
        return {
            "inserted": 0,
            "events_seen": 0,
            "events_processed": 0,
            "snapshots_inserted": 0,
            "event_ids": [],
            "event_ids_updated": [],
            "consensus_points_written": 0,
            "consensus_failed": False,
            "api_requests_remaining": api_requests_remaining,
            "api_requests_used": api_requests_used,
            "api_requests_last": api_requests_last,
            "api_requests_limit": api_requests_limit,
            "sports_polled": sport_keys,
            "events_seen_by_sport": per_sport_events_seen,
        }

    fetched_at = datetime.now(UTC)
    inserted = 0
    event_ids: set[str] = set()
    consensus_points_written = 0
    consensus_failed = False
    persisted_snapshots: list[OddsSnapshot] = []
    commence_time_map: dict[str, datetime] = {}

    allowed_markets = {"spreads", "totals", "h2h"}
    for event in events:
        try:
            await _upsert_game(db, event)
            event_id = event["id"]
            event_ids.add(event_id)
            commence_time_map[event_id] = _parse_iso_datetime(event["commence_time"])
            normalized_rows = normalize_event_odds_rows(
                event,
                fetched_at=fetched_at,
                allowed_markets=allowed_markets,
            )
        except KeyError:
            logger.warning("Malformed event payload skipped", extra={"event": event})
            continue

        for row in normalized_rows:
            dedupe_key = (
                f"odds:last:{row.event_id}:{row.sportsbook_key}:{row.market}:{row.outcome_name}"
            )
            dedupe_value = f"{row.line}|{row.price}"

            should_persist = await _should_persist_snapshot(
                redis,
                dedupe_key=dedupe_key,
                dedupe_value=dedupe_value,
            )
            if not should_persist:
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
            persisted_snapshots.append(snapshot)
            inserted += 1

            # Broadcast update via Redis Pub/Sub
            if redis is not None:
                import json
                update_payload = {
                    "type": "odds_update",
                    "event_id": row.event_id,
                    "sportsbook": row.sportsbook_key,
                    "market": row.market,
                    "outcome": row.outcome_name,
                    "line": row.line,
                    "price": row.price,
                    "timestamp": row.fetched_at.isoformat(),
                }
                await redis.publish("odds_updates", json.dumps(update_payload))

    await db.commit()

    # --- Quote Move Ledger (additive) ---
    quote_moves_logged = 0
    if persisted_snapshots:
        try:
            moves = await detect_quote_moves(db, persisted_snapshots, commence_time_map)
            quote_moves_logged = len(moves)
            if moves:
                await db.commit()
        except Exception:
            logger.exception("Quote move detection failed; continuing")

    if settings.consensus_enabled and event_ids:
        try:
            consensus_points_written = await compute_and_persist_consensus(db, list(event_ids))
        except Exception:
            logger.exception("Consensus computation failed; continuing without consensus snapshots")
            consensus_failed = True

    logger.info(
        "Odds ingestion cycle completed",
        extra={
            "inserted": inserted,
            "events_seen": len(events),
            "consensus_points_written": consensus_points_written,
            "api_requests_remaining": api_requests_remaining,
            "api_requests_used": api_requests_used,
            "api_requests_last": api_requests_last,
            "api_requests_limit": api_requests_limit,
            "sports_polled": sport_keys,
            "events_seen_by_sport": per_sport_events_seen,
            "consensus_failed": consensus_failed,
        },
    )
    return {
        "inserted": inserted,
        "events_seen": len(events),
        "events_processed": len(events),
        "snapshots_inserted": inserted,
        "event_ids": list(event_ids),
        "event_ids_updated": list(event_ids),
        "consensus_points_written": consensus_points_written,
        "consensus_failed": consensus_failed,
        "api_requests_remaining": api_requests_remaining,
        "api_requests_used": api_requests_used,
        "api_requests_last": api_requests_last,
        "api_requests_limit": api_requests_limit,
        "sports_polled": sport_keys,
        "events_seen_by_sport": per_sport_events_seen,
        "quote_moves_logged": quote_moves_logged,
    }
