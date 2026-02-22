from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.services.consensus import (
    cleanup_old_consensus_snapshots,
    compute_and_persist_consensus,
    dispersion_stddev,
    latest_snapshots_for_event,
)


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    market: str,
    outcome_name: str,
    price: int,
    line: float | None,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=2),
        home_team="BOS",
        away_team="NYK",
        sportsbook_key=sportsbook_key,
        market=market,
        outcome_name=outcome_name,
        line=line,
        price=price,
        fetched_at=fetched_at,
    )


def test_dispersion_stddev_returns_none_for_single_point() -> None:
    assert dispersion_stddev([10.5]) is None


async def test_latest_snapshots_for_event_dedupes_to_latest_per_book_outcome(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_consensus_dedupe"
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                market="spreads",
                outcome_name="BOS",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=5),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                market="spreads",
                outcome_name="BOS",
                line=-4.0,
                price=-112,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book2",
                market="spreads",
                outcome_name="BOS",
                line=-3.5,
                price=-108,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                market="spreads",
                outcome_name="NYK",
                line=4.0,
                price=-108,
                fetched_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.flush()

    latest = await latest_snapshots_for_event(db_session, event_id, "spreads", lookback_minutes=10)
    latest_map = {(snap.sportsbook_key, snap.outcome_name): snap for snap in latest}

    assert len(latest_map) == 3
    assert latest_map[("book1", "BOS")].line == -4.0
    assert latest_map[("book2", "BOS")].line == -3.5
    assert latest_map[("book1", "NYK")].line == 4.0


async def test_compute_and_persist_consensus_creates_rows_when_min_books_met(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_consensus_full"
    books = ["book1", "book2", "book3", "book4", "book5"]

    home_spread_lines = [-3.0, -3.5, -4.0, -3.5, -3.0]
    away_spread_lines = [3.0, 3.5, 4.0, 3.5, 3.0]
    total_lines = [220.5, 221.0, 221.5, 221.0, 220.5]
    home_h2h_prices = [-120, -118, -122, -121, -119]
    away_h2h_prices = [110, 108, 112, 111, 109]

    seeded: list[OddsSnapshot] = []
    for idx, book in enumerate(books):
        t = now - timedelta(minutes=idx)
        seeded.extend(
            [
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="spreads",
                    outcome_name="BOS",
                    line=home_spread_lines[idx],
                    price=-110,
                    fetched_at=t,
                ),
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="spreads",
                    outcome_name="NYK",
                    line=away_spread_lines[idx],
                    price=-110,
                    fetched_at=t,
                ),
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="totals",
                    outcome_name="Over",
                    line=total_lines[idx],
                    price=-110,
                    fetched_at=t,
                ),
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="totals",
                    outcome_name="Under",
                    line=total_lines[idx],
                    price=-110,
                    fetched_at=t,
                ),
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="h2h",
                    outcome_name="BOS",
                    line=None,
                    price=home_h2h_prices[idx],
                    fetched_at=t,
                ),
                _snapshot(
                    event_id=event_id,
                    sportsbook_key=book,
                    market="h2h",
                    outcome_name="NYK",
                    line=None,
                    price=away_h2h_prices[idx],
                    fetched_at=t,
                ),
            ]
        )

    db_session.add_all(seeded)
    await db_session.flush()

    inserted = await compute_and_persist_consensus(db_session, [event_id])
    assert inserted == 6

    rows = (
        await db_session.execute(
            select(MarketConsensusSnapshot).where(MarketConsensusSnapshot.event_id == event_id)
        )
    ).scalars().all()

    assert len(rows) == 6
    row_map = {(row.market, row.outcome_name): row for row in rows}

    home_spread = row_map[("spreads", "BOS")]
    assert home_spread.consensus_line == -3.5
    assert home_spread.consensus_price == -110.0
    assert home_spread.dispersion is not None
    assert home_spread.books_count == 5

    home_h2h = row_map[("h2h", "BOS")]
    assert home_h2h.consensus_line is None
    assert home_h2h.consensus_price == -120.0
    assert home_h2h.dispersion is not None
    assert home_h2h.books_count == 5


async def test_compute_and_persist_consensus_skips_when_books_below_min(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONSENSUS_MIN_BOOKS", "4")
    monkeypatch.setenv("CONSENSUS_MIN_MARKETS", "1")

    now = datetime.now(UTC)
    event_id = "event_consensus_low_books"
    books = ["book1", "book2", "book3"]

    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="h2h",
                outcome_name="BOS",
                line=None,
                price=-120,
                fetched_at=now - timedelta(minutes=i),
            )
            for i, book in enumerate(books)
        ]
        + [
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="h2h",
                outcome_name="NYK",
                line=None,
                price=110,
                fetched_at=now - timedelta(minutes=i),
            )
            for i, book in enumerate(books)
        ]
    )
    await db_session.flush()

    inserted = await compute_and_persist_consensus(db_session, [event_id])
    assert inserted == 0

    rows = (
        await db_session.execute(
            select(MarketConsensusSnapshot).where(MarketConsensusSnapshot.event_id == event_id)
        )
    ).scalars().all()
    assert rows == []


async def test_cleanup_old_consensus_snapshots_deletes_only_expired_rows(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            MarketConsensusSnapshot(
                event_id="event_cleanup",
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.5,
                books_count=5,
                fetched_at=now - timedelta(days=30),
            ),
            MarketConsensusSnapshot(
                event_id="event_cleanup",
                market="spreads",
                outcome_name="NYK",
                consensus_line=3.5,
                consensus_price=-110.0,
                dispersion=0.5,
                books_count=5,
                fetched_at=now - timedelta(days=2),
            ),
        ]
    )
    await db_session.commit()

    deleted = await cleanup_old_consensus_snapshots(db_session, retention_days=14)
    assert deleted == 1

    remaining = (await db_session.execute(select(MarketConsensusSnapshot))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].outcome_name == "NYK"
