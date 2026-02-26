from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median as stats_median

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import AsyncSessionLocal
from app.models.closing_consensus import ClosingConsensus
from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.ingestion import NormalizedOddsRow, normalize_event_odds_rows
from app.services.odds_api import fetch_nba_odds_history

logger = logging.getLogger(__name__)

CANONICAL_MARKETS = {"spreads", "totals", "h2h"}
FINISHED_GAME_BUFFER_HOURS = 4
HISTORY_OFFSETS_MINUTES = (
    -180,
    -120,
    -90,
    -60,
    -45,
    -30,
    -20,
    -10,
    -5,
    0,
    5,
    10,
    20,
    30,
    45,
    60,
)


@dataclass(frozen=True)
class _ClosePoint:
    market: str
    outcome_name: str
    close_line: float | None
    close_price: float | None
    close_fetched_at: datetime
    close_inferred: bool


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(stats_median(values))


def _coerce_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return fallback
    return fallback


def _history_dates_around_tipoff(tipoff: datetime) -> list[datetime]:
    base = tipoff.astimezone(UTC) if tipoff.tzinfo else tipoff.replace(tzinfo=UTC)
    return [base + timedelta(minutes=offset) for offset in HISTORY_OFFSETS_MINUTES]


def _row_key(row: NormalizedOddsRow) -> tuple[str, str, str, str, float | None, int, datetime]:
    fetched_at = row.fetched_at.astimezone(UTC) if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
    return (
        row.market,
        row.outcome_name,
        row.sportsbook_key,
        row.event_id,
        row.line,
        row.price,
        fetched_at,
    )


async def _observed_markets_for_event(
    db: AsyncSession,
    *,
    event_id: str,
) -> set[str]:
    signal_markets_stmt = (
        select(Signal.market)
        .where(
            Signal.event_id == event_id,
            Signal.market.in_(CANONICAL_MARKETS),
        )
        .distinct()
    )
    snapshot_markets_stmt = (
        select(OddsSnapshot.market)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market.in_(CANONICAL_MARKETS),
        )
        .distinct()
    )
    signal_markets = {
        market
        for market in (await db.execute(signal_markets_stmt)).scalars().all()
        if isinstance(market, str) and market in CANONICAL_MARKETS
    }
    snapshot_markets = {
        market
        for market in (await db.execute(snapshot_markets_stmt)).scalars().all()
        if isinstance(market, str) and market in CANONICAL_MARKETS
    }
    return signal_markets | snapshot_markets


async def _existing_close_markets_for_event(
    db: AsyncSession,
    *,
    event_id: str,
) -> set[str]:
    stmt = (
        select(ClosingConsensus.market)
        .where(
            ClosingConsensus.event_id == event_id,
            ClosingConsensus.market.in_(CANONICAL_MARKETS),
        )
        .distinct()
    )
    return {
        market
        for market in (await db.execute(stmt)).scalars().all()
        if isinstance(market, str) and market in CANONICAL_MARKETS
    }


async def _fetch_history_rows_for_event(
    *,
    event_id: str,
    sport_key: str,
    tipoff: datetime,
    markets: set[str],
    settings: Settings,
) -> list[NormalizedOddsRow]:
    bookmakers = [book.strip() for book in settings.odds_api_bookmakers.split(",") if book.strip()]
    allowed_markets = {market for market in markets if market in CANONICAL_MARKETS}
    seen_keys: set[tuple[str, str, str, str, float | None, int, datetime]] = set()
    rows: list[NormalizedOddsRow] = []

    for history_date in _history_dates_around_tipoff(tipoff):
        payload = await fetch_nba_odds_history(
            event_id=event_id,
            sport_key=sport_key,
            endpoint_variant="event",
            markets=sorted(allowed_markets),
            regions=settings.odds_api_regions,
            bookmakers=bookmakers or None,
            date=history_date,
        )

        history_timestamp = _coerce_datetime(payload.get("history_timestamp"), fallback=history_date)
        history_events = payload.get("events", [])
        if not isinstance(history_events, list):
            continue

        for event in history_events:
            if not isinstance(event, dict):
                continue
            if event.get("id") != event_id:
                continue

            normalized_rows = normalize_event_odds_rows(
                event,
                fetched_at=history_timestamp,
                allowed_markets=allowed_markets,
            )
            for row in normalized_rows:
                key = _row_key(row)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(row)

    return rows


def _compute_close_points(
    *,
    rows: list[NormalizedOddsRow],
    tipoff: datetime,
    allowed_markets: set[str],
) -> list[_ClosePoint]:
    tipoff_utc = tipoff.astimezone(UTC) if tipoff.tzinfo else tipoff.replace(tzinfo=UTC)
    grouped_rows: dict[tuple[str, str], dict[datetime, list[NormalizedOddsRow]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for row in rows:
        if row.market not in allowed_markets:
            continue
        fetched_at = row.fetched_at.astimezone(UTC) if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
        grouped_rows[(row.market, row.outcome_name)][fetched_at].append(row)

    close_points: list[_ClosePoint] = []
    for (market, outcome_name), by_timestamp in grouped_rows.items():
        timestamps = sorted(by_timestamp.keys())
        if not timestamps:
            continue

        timestamps_at_or_before_tipoff = [ts for ts in timestamps if ts <= tipoff_utc]
        if timestamps_at_or_before_tipoff:
            selected_timestamp = timestamps_at_or_before_tipoff[-1]
            close_inferred = False
        else:
            selected_timestamp = timestamps[0]
            close_inferred = True

        selected_rows = by_timestamp[selected_timestamp]
        prices = [float(row.price) for row in selected_rows]
        lines = [float(row.line) for row in selected_rows if row.line is not None]

        close_line = None if market == "h2h" else _median(lines)
        close_price = _median(prices)

        if close_line is None and close_price is None:
            continue

        close_points.append(
            _ClosePoint(
                market=market,
                outcome_name=outcome_name,
                close_line=close_line,
                close_price=close_price,
                close_fetched_at=selected_timestamp,
                close_inferred=close_inferred,
            )
        )

    return close_points


async def _upsert_close_points(
    db: AsyncSession,
    *,
    event_id: str,
    close_points: list[_ClosePoint],
) -> int:
    now = datetime.now(UTC)
    upserts = 0
    for close_point in close_points:
        upsert_stmt = pg_insert(ClosingConsensus).values(
            event_id=event_id,
            market=close_point.market,
            outcome_name=close_point.outcome_name,
            close_line=close_point.close_line,
            close_price=close_point.close_price,
            close_fetched_at=close_point.close_fetched_at,
            computed_at=now,
        )
        upsert_stmt = upsert_stmt.on_conflict_do_update(
            index_elements=["event_id", "market", "outcome_name"],
            set_={
                "close_line": upsert_stmt.excluded.close_line,
                "close_price": upsert_stmt.excluded.close_price,
                "close_fetched_at": upsert_stmt.excluded.close_fetched_at,
                "computed_at": upsert_stmt.excluded.computed_at,
            },
        )
        await db.execute(upsert_stmt)
        upserts += 1

    return upserts


async def _run_backfill(
    db: AsyncSession,
    *,
    lookback_hours: int,
    max_games: int,
    settings: Settings,
) -> dict:
    metrics: dict[str, int] = {
        "games_scanned": 0,
        "games_backfilled": 0,
        "games_skipped": 0,
        "errors": 0,
    }
    if max_games <= 0:
        logger.info("Historical backfill completed", extra=metrics)
        return metrics

    now = datetime.now(UTC)
    lookback_start = now - timedelta(hours=max(1, lookback_hours))
    finished_cutoff = now - timedelta(hours=FINISHED_GAME_BUFFER_HOURS)
    search_limit = max(max_games * 4, max_games)

    has_signal = exists(select(1).where(Signal.event_id == Game.event_id))
    has_snapshot = exists(select(1).where(OddsSnapshot.event_id == Game.event_id))
    games_stmt = (
        select(Game)
        .where(
            Game.commence_time >= lookback_start,
            Game.commence_time <= finished_cutoff,
            has_signal | has_snapshot,
        )
        .order_by(Game.commence_time.desc(), Game.event_id.asc())
        .limit(search_limit)
    )
    candidate_games = (await db.execute(games_stmt)).scalars().all()
    if not candidate_games:
        logger.info("Historical backfill completed", extra=metrics)
        return metrics

    configured_markets = {market for market in settings.consensus_markets_list if market in CANONICAL_MARKETS}
    default_markets = configured_markets or set(CANONICAL_MARKETS)
    close_cutoff = settings.clv_close_cutoff.strip().upper()
    if close_cutoff != "TIPOFF":
        logger.warning(
            "Unsupported CLV close cutoff configured; defaulting to TIPOFF",
            extra={"configured_close_cutoff": settings.clv_close_cutoff},
        )
        close_cutoff = "TIPOFF"

    processed_games = 0
    for game in candidate_games:
        metrics["games_scanned"] += 1
        if processed_games >= max_games:
            break

        try:
            observed_markets = await _observed_markets_for_event(db, event_id=game.event_id)
            markets_to_consider = observed_markets or set(default_markets)
            existing_close_markets = await _existing_close_markets_for_event(db, event_id=game.event_id)
            missing_markets = markets_to_consider - existing_close_markets
            missing_markets = {market for market in missing_markets if market in CANONICAL_MARKETS}

            if not missing_markets:
                metrics["games_skipped"] += 1
                continue

            processed_games += 1
            history_rows = await _fetch_history_rows_for_event(
                event_id=game.event_id,
                sport_key=game.sport_key,
                tipoff=game.commence_time,
                markets=missing_markets,
                settings=settings,
            )
            if not history_rows:
                logger.warning(
                    "Historical backfill found no usable history snapshots",
                    extra={
                        "event_id": game.event_id,
                        "markets": sorted(missing_markets),
                    },
                )
                metrics["games_skipped"] += 1
                continue

            close_points = _compute_close_points(
                rows=history_rows,
                tipoff=game.commence_time,
                allowed_markets=missing_markets,
            )
            if not close_points:
                logger.warning(
                    "Historical backfill could not derive close points",
                    extra={
                        "event_id": game.event_id,
                        "markets": sorted(missing_markets),
                    },
                )
                metrics["games_skipped"] += 1
                continue

            for point in close_points:
                if point.close_inferred:
                    logger.warning(
                        "Historical backfill inferred close from post-tipoff snapshot",
                        extra={
                            "event_id": game.event_id,
                            "market": point.market,
                            "outcome_name": point.outcome_name,
                            "close_fetched_at": point.close_fetched_at.isoformat(),
                            "close_cutoff": close_cutoff,
                        },
                    )

            upserts = await _upsert_close_points(db, event_id=game.event_id, close_points=close_points)
            if upserts > 0:
                await db.commit()
                metrics["games_backfilled"] += 1
            else:
                metrics["games_skipped"] += 1
        except Exception:
            await db.rollback()
            logger.exception(
                "Historical backfill failed for event",
                extra={"event_id": game.event_id},
            )
            metrics["errors"] += 1
            metrics["games_skipped"] += 1

    logger.info("Historical backfill completed", extra=metrics)
    return metrics


async def backfill_missing_closing_consensus(
    *,
    lookback_hours: int,
    max_games: int,
    settings: Settings,
    db: AsyncSession | None = None,
) -> dict:
    """
    Find recently finished games missing closing consensus, fetch historical odds,
    derive close snapshots at tipoff cutoff, and upsert ClosingConsensus rows.
    """
    if db is not None:
        return await _run_backfill(
            db,
            lookback_hours=lookback_hours,
            max_games=max_games,
            settings=settings,
        )

    async with AsyncSessionLocal() as session:
        return await _run_backfill(
            session,
            lookback_hours=lookback_hours,
            max_games=max_games,
            settings=settings,
        )
