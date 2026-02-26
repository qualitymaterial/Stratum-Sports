"""Tests for the quote move detection service."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
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


async def test_detect_quote_moves_creates_event_on_line_change(
    db_session: AsyncSession,
) -> None:
    """A line change between two snapshots should produce a QuoteMoveEvent."""
    now = datetime.now(UTC)
    event_id = "evt_qm_line"

    # Previous snapshot (already in DB)
    prev = _snapshot(
        event_id=event_id,
        sportsbook_key="pinnacle",
        market="spreads",
        outcome_name="BOS",
        line=-3.0,
        price=-110,
        fetched_at=now - timedelta(minutes=5),
    )
    db_session.add(prev)
    await db_session.flush()

    # New snapshot with changed line
    new_snap = _snapshot(
        event_id=event_id,
        sportsbook_key="pinnacle",
        market="spreads",
        outcome_name="BOS",
        line=-3.5,
        price=-110,
        fetched_at=now,
    )
    db_session.add(new_snap)
    await db_session.flush()

    commence_times = {event_id: now + timedelta(hours=2)}
    moves = await detect_quote_moves(db_session, [new_snap], commence_times)

    assert len(moves) == 1
    move = moves[0]
    assert move.event_id == event_id
    assert move.market_key == "spreads"
    assert move.outcome_name == "BOS"
    assert move.venue == "pinnacle"
    assert move.venue_tier == "T1"
    assert move.old_line == -3.0
    assert move.new_line == -3.5
    assert move.delta == -0.5
    assert move.price_delta == 0.0  # price unchanged
    assert move.minutes_to_tip is not None


async def test_detect_quote_moves_creates_event_on_price_change(
    db_session: AsyncSession,
) -> None:
    """A price-only change should also produce a QuoteMoveEvent."""
    now = datetime.now(UTC)
    event_id = "evt_qm_price"

    prev = _snapshot(
        event_id=event_id,
        sportsbook_key="draftkings",
        market="h2h",
        outcome_name="BOS",
        line=None,
        price=-120,
        fetched_at=now - timedelta(minutes=5),
    )
    db_session.add(prev)
    await db_session.flush()

    new_snap = _snapshot(
        event_id=event_id,
        sportsbook_key="draftkings",
        market="h2h",
        outcome_name="BOS",
        line=None,
        price=-115,
        fetched_at=now,
    )
    db_session.add(new_snap)
    await db_session.flush()

    moves = await detect_quote_moves(db_session, [new_snap], {})

    assert len(moves) == 1
    move = moves[0]
    assert move.venue == "draftkings"
    assert move.venue_tier == "T3"
    assert move.delta is None  # both lines are None
    assert move.price_delta == 5.0
    assert move.minutes_to_tip is None  # no commence_time provided


async def test_detect_quote_moves_skips_when_no_change(
    db_session: AsyncSession,
) -> None:
    """Identical snapshots should produce no QuoteMoveEvent."""
    now = datetime.now(UTC)
    event_id = "evt_qm_nochange"

    prev = _snapshot(
        event_id=event_id,
        sportsbook_key="fanduel",
        market="spreads",
        outcome_name="BOS",
        line=-3.0,
        price=-110,
        fetched_at=now - timedelta(minutes=5),
    )
    db_session.add(prev)
    await db_session.flush()

    new_snap = _snapshot(
        event_id=event_id,
        sportsbook_key="fanduel",
        market="spreads",
        outcome_name="BOS",
        line=-3.0,
        price=-110,
        fetched_at=now,
    )
    db_session.add(new_snap)
    await db_session.flush()

    moves = await detect_quote_moves(db_session, [new_snap], {})
    assert len(moves) == 0


async def test_detect_quote_moves_skips_first_snapshot(
    db_session: AsyncSession,
) -> None:
    """A snapshot with no prior should produce no QuoteMoveEvent."""
    now = datetime.now(UTC)
    event_id = "evt_qm_first"

    new_snap = _snapshot(
        event_id=event_id,
        sportsbook_key="pinnacle",
        market="spreads",
        outcome_name="BOS",
        line=-3.0,
        price=-110,
        fetched_at=now,
    )
    db_session.add(new_snap)
    await db_session.flush()

    moves = await detect_quote_moves(db_session, [new_snap], {})
    assert len(moves) == 0


async def test_detect_quote_moves_returns_empty_for_empty_input(
    db_session: AsyncSession,
) -> None:
    """Empty snapshot list returns empty moves list."""
    moves = await detect_quote_moves(db_session, [], {})
    assert moves == []


async def test_detect_quote_moves_multiple_venues(
    db_session: AsyncSession,
) -> None:
    """Multiple venues moving should each produce their own QuoteMoveEvent."""
    now = datetime.now(UTC)
    event_id = "evt_qm_multi"
    venues = ["pinnacle", "draftkings", "fanduel"]

    # Seed previous snapshots
    for venue in venues:
        db_session.add(
            _snapshot(
                event_id=event_id,
                sportsbook_key=venue,
                market="spreads",
                outcome_name="BOS",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=5),
            )
        )
    await db_session.flush()

    # New snapshots: pinnacle and fanduel change line, draftkings stays the same
    new_snaps = []
    for venue, line in [("pinnacle", -3.5), ("draftkings", -3.0), ("fanduel", -4.0)]:
        snap = _snapshot(
            event_id=event_id,
            sportsbook_key=venue,
            market="spreads",
            outcome_name="BOS",
            line=line,
            price=-110,
            fetched_at=now,
        )
        db_session.add(snap)
        new_snaps.append(snap)
    await db_session.flush()

    moves = await detect_quote_moves(db_session, new_snaps, {})

    assert len(moves) == 2
    move_venues = {m.venue for m in moves}
    assert move_venues == {"pinnacle", "fanduel"}
