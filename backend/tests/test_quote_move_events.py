from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
from app.models.quote_move_event import QuoteMoveEvent
from app.services.quote_moves import detect_quote_moves


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


async def test_quote_move_event_created_for_line_change(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "evt_qm_ledger_line"

    previous = _snapshot(
        event_id=event_id,
        sportsbook_key="pinnacle",
        market="spreads",
        outcome_name="BOS",
        line=-3.0,
        price=-110,
        fetched_at=now - timedelta(minutes=5),
    )
    current = _snapshot(
        event_id=event_id,
        sportsbook_key="pinnacle",
        market="spreads",
        outcome_name="BOS",
        line=-4.0,
        price=-110,
        fetched_at=now,
    )

    db_session.add(previous)
    db_session.add(current)
    await db_session.flush()

    await detect_quote_moves(db_session, [current], {event_id: now + timedelta(hours=2)})
    await db_session.flush()

    rows = (await db_session.execute(select(QuoteMoveEvent).where(QuoteMoveEvent.event_id == event_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].delta == -1.0
    assert rows[0].price_delta == 0.0


async def test_quote_move_event_created_for_price_only_change(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "evt_qm_ledger_price"

    previous = _snapshot(
        event_id=event_id,
        sportsbook_key="draftkings",
        market="h2h",
        outcome_name="BOS",
        line=None,
        price=-125,
        fetched_at=now - timedelta(minutes=5),
    )
    current = _snapshot(
        event_id=event_id,
        sportsbook_key="draftkings",
        market="h2h",
        outcome_name="BOS",
        line=None,
        price=-118,
        fetched_at=now,
    )

    db_session.add(previous)
    db_session.add(current)
    await db_session.flush()

    await detect_quote_moves(db_session, [current], {})
    await db_session.flush()

    rows = (await db_session.execute(select(QuoteMoveEvent).where(QuoteMoveEvent.event_id == event_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].delta is None
    assert rows[0].price_delta == 7.0
