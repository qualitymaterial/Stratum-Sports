import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median as stats_median
from statistics import pstdev

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot

logger = logging.getLogger(__name__)

CANONICAL_MARKETS = {"spreads", "totals", "h2h"}


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _consensus_thresholds() -> tuple[int, int]:
    min_books = _read_int_env("CONSENSUS_MIN_BOOKS", 4)
    min_markets = _read_int_env("CONSENSUS_MIN_MARKETS", 1)
    return max(1, min_books), max(1, min_markets)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(stats_median(values))


def dispersion_stddev(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return None
    return float(pstdev(values))


async def latest_snapshots_for_event(
    session: AsyncSession,
    event_id: str,
    market: str,
    lookback_minutes: int,
) -> list[OddsSnapshot]:
    cutoff = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.market == market,
            OddsSnapshot.fetched_at >= cutoff,
        )
        .order_by(
            desc(OddsSnapshot.fetched_at),
            OddsSnapshot.sportsbook_key.asc(),
            OddsSnapshot.outcome_name.asc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()

    latest_by_book_outcome: dict[tuple[str, str], OddsSnapshot] = {}
    for snap in rows:
        key = (snap.sportsbook_key, snap.outcome_name)
        if key in latest_by_book_outcome:
            continue
        latest_by_book_outcome[key] = snap

    return sorted(
        latest_by_book_outcome.values(),
        key=lambda s: (s.outcome_name, s.sportsbook_key),
    )


async def compute_and_persist_consensus(session: AsyncSession, event_ids: list[str]) -> int:
    settings = get_settings()
    if not settings.consensus_enabled or not event_ids:
        return 0

    configured_markets = [m for m in settings.consensus_markets_list if m in CANONICAL_MARKETS]
    if not configured_markets:
        return 0

    min_books, min_markets = _consensus_thresholds()

    points_written = 0
    skipped_insufficient_books = 0
    skipped_insufficient_markets = 0
    events_processed = 0

    run_fetched_at = datetime.now(UTC)

    for event_id in sorted(set(event_ids)):
        events_processed += 1
        latest_by_market: dict[str, list[OddsSnapshot]] = {}
        markets_seen = 0
        eligible_markets = 0

        for market in configured_markets:
            latest = await latest_snapshots_for_event(
                session,
                event_id=event_id,
                market=market,
                lookback_minutes=settings.consensus_lookback_minutes,
            )
            if not latest:
                continue

            markets_seen += 1
            books_available = len({snap.sportsbook_key for snap in latest})
            if books_available < min_books:
                skipped_insufficient_books += 1
                logger.info(
                    "Consensus skipped: insufficient books",
                    extra={
                        "event_id": event_id,
                        "market": market,
                        "books_available": books_available,
                        "min_books_required": min_books,
                    },
                )
                continue

            latest_by_market[market] = latest
            eligible_markets += 1

        if eligible_markets < min_markets:
            skipped_insufficient_markets += 1
            logger.info(
                "Consensus skipped: insufficient eligible markets",
                extra={
                    "event_id": event_id,
                    "eligible_markets": eligible_markets,
                    "min_markets_required": min_markets,
                    "markets_seen": markets_seen,
                },
            )
            continue

        for market in configured_markets:
            latest = latest_by_market.get(market)
            if not latest:
                continue

            by_outcome: dict[str, list[OddsSnapshot]] = defaultdict(list)
            for snapshot in latest:
                by_outcome[snapshot.outcome_name].append(snapshot)

            for outcome_name in sorted(by_outcome.keys()):
                outcome_snaps = by_outcome[outcome_name]
                books = {snap.sportsbook_key for snap in outcome_snaps}
                books_count = len(books)

                if books_count < min_books:
                    skipped_insufficient_books += 1
                    logger.info(
                        "Consensus skipped: insufficient books",
                        extra={
                            "event_id": event_id,
                            "market": market,
                            "outcome_name": outcome_name,
                            "books_available": books_count,
                            "min_books_required": min_books,
                        },
                    )
                    continue

                prices = [float(snap.price) for snap in outcome_snaps]
                lines = [float(snap.line) for snap in outcome_snaps if snap.line is not None]

                if market == "h2h":
                    consensus_line = None
                    consensus_price = median(prices)
                    dispersion = dispersion_stddev(prices)
                else:
                    consensus_line = median(lines)
                    consensus_price = median(prices) if prices else None
                    dispersion = dispersion_stddev(lines)

                session.add(
                    MarketConsensusSnapshot(
                        event_id=event_id,
                        market=market,
                        outcome_name=outcome_name,
                        consensus_line=consensus_line,
                        consensus_price=consensus_price,
                        dispersion=dispersion,
                        books_count=books_count,
                        fetched_at=run_fetched_at,
                    )
                )
                points_written += 1

    if points_written > 0:
        await session.commit()

    logger.info(
        "Consensus computation completed",
        extra={
            "consensus_points_written": points_written,
            "consensus_events_processed": events_processed,
            "consensus_skipped_insufficient_books": skipped_insufficient_books,
            "consensus_skipped_insufficient_markets": skipped_insufficient_markets,
            "consensus_min_books_required": min_books,
            "consensus_min_markets_required": min_markets,
        },
    )

    return points_written


async def cleanup_old_consensus_snapshots(
    session: AsyncSession,
    retention_days: int | None = None,
) -> int:
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.consensus_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = delete(MarketConsensusSnapshot).where(MarketConsensusSnapshot.fetched_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0
