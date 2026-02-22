import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.services.consensus import compute_and_persist_consensus


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    outcome_name: str,
    price: int,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=2),
        home_team="BOS",
        away_team="NYK",
        sportsbook_key=sportsbook_key,
        market="h2h",
        outcome_name=outcome_name,
        line=None,
        price=price,
        fetched_at=fetched_at,
    )


async def test_consensus_min_books_two_writes_points(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONSENSUS_MIN_BOOKS", "2")
    monkeypatch.setenv("CONSENSUS_MIN_MARKETS", "1")

    now = datetime.now(UTC)
    event_id = "event_consensus_threshold_two_books"
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                outcome_name="BOS",
                price=-120,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book2",
                outcome_name="BOS",
                price=-118,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                outcome_name="NYK",
                price=110,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book2",
                outcome_name="NYK",
                price=108,
                fetched_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await db_session.flush()

    inserted = await compute_and_persist_consensus(db_session, [event_id])
    assert inserted >= 1

    rows = (
        await db_session.execute(
            select(MarketConsensusSnapshot).where(MarketConsensusSnapshot.event_id == event_id)
        )
    ).scalars().all()
    assert len(rows) >= 1


async def test_consensus_min_books_four_skips_two_book_market(
    db_session: AsyncSession,
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("CONSENSUS_MIN_BOOKS", "4")
    monkeypatch.setenv("CONSENSUS_MIN_MARKETS", "1")

    now = datetime.now(UTC)
    event_id = "event_consensus_threshold_four_books"
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                outcome_name="BOS",
                price=-120,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book2",
                outcome_name="BOS",
                price=-118,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book1",
                outcome_name="NYK",
                price=110,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="book2",
                outcome_name="NYK",
                price=108,
                fetched_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await db_session.flush()

    with caplog.at_level(logging.INFO):
        inserted = await compute_and_persist_consensus(db_session, [event_id])

    assert inserted == 0
    rows = (
        await db_session.execute(
            select(MarketConsensusSnapshot).where(MarketConsensusSnapshot.event_id == event_id)
        )
    ).scalars().all()
    assert rows == []
    assert any("Consensus skipped: insufficient books" in record.message for record in caplog.records)
