import logging
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.odds_api import OddsApiClient

logger = logging.getLogger(__name__)


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


async def ingest_odds_cycle(db: AsyncSession, redis: Redis | None) -> dict:
    client = OddsApiClient()
    fetch_result = await client.fetch_nba_odds()
    events = fetch_result.events
    if not events:
        return {
            "inserted": 0,
            "events_seen": 0,
            "event_ids": [],
            "api_requests_remaining": fetch_result.requests_remaining,
            "api_requests_used": fetch_result.requests_used,
            "api_requests_last": fetch_result.requests_last,
        }

    fetched_at = datetime.now(UTC)
    inserted = 0
    event_ids: set[str] = set()

    for event in events:
        try:
            await _upsert_game(db, event)
            event_id = event["id"]
            event_ids.add(event_id)
        except KeyError:
            logger.warning("Malformed event payload skipped", extra={"event": event})
            continue

        bookmakers = event.get("bookmakers", [])
        for bookmaker in bookmakers:
            sportsbook_key = bookmaker.get("key")
            if not sportsbook_key:
                continue

            for market_entry in bookmaker.get("markets", []):
                market = market_entry.get("key")
                if market not in {"spreads", "totals", "h2h"}:
                    continue

                for outcome in market_entry.get("outcomes", []):
                    outcome_name = outcome.get("name")
                    price = outcome.get("price")
                    if outcome_name is None or price is None:
                        continue

                    line = _normalize_line(market, outcome)
                    dedupe_key = (
                        f"odds:last:{event_id}:{sportsbook_key}:{market}:{outcome_name}"
                    )
                    dedupe_value = f"{line}|{int(price)}"

                    try:
                        if redis is not None:
                            previous_value = await redis.get(dedupe_key)
                            if previous_value == dedupe_value:
                                continue
                            await redis.set(dedupe_key, dedupe_value, ex=60 * 60 * 24)
                    except Exception:
                        logger.exception("Redis dedupe failed; continuing without dedupe")

                    snapshot = OddsSnapshot(
                        event_id=event_id,
                        sport_key=event.get("sport_key", "basketball_nba"),
                        commence_time=_parse_iso_datetime(event["commence_time"]),
                        home_team=event["home_team"],
                        away_team=event["away_team"],
                        sportsbook_key=sportsbook_key,
                        market=market,
                        outcome_name=outcome_name,
                        line=line,
                        price=int(price),
                        fetched_at=fetched_at,
                    )
                    db.add(snapshot)
                    inserted += 1

                    # Broadcast update via Redis Pub/Sub
                    if redis is not None:
                        import json
                        update_payload = {
                            "type": "odds_update",
                            "event_id": event_id,
                            "sportsbook": sportsbook_key,
                            "market": market,
                            "outcome": outcome_name,
                            "line": line,
                            "price": int(price),
                            "timestamp": fetched_at.isoformat(),
                        }
                        await redis.publish("odds_updates", json.dumps(update_payload))

    await db.commit()

    logger.info(
        "Odds ingestion cycle completed",
        extra={
            "inserted": inserted,
            "events_seen": len(events),
            "api_requests_remaining": fetch_result.requests_remaining,
            "api_requests_used": fetch_result.requests_used,
            "api_requests_last": fetch_result.requests_last,
        },
    )
    return {
        "inserted": inserted,
        "events_seen": len(events),
        "event_ids": list(event_ids),
        "api_requests_remaining": fetch_result.requests_remaining,
        "api_requests_used": fetch_result.requests_used,
        "api_requests_last": fetch_result.requests_last,
    }
