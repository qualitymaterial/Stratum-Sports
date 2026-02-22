from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_snapshot import OddsSnapshot
from app.services.signals import detect_steam_v2


class FakeRedis:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._keys:
            return None
        self._keys[key] = value
        return True


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    market: str,
    outcome_name: str,
    line: float,
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
        price=-110,
        fetched_at=fetched_at,
    )


async def test_steam_created_for_fast_synchronized_move(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_steam_positive"
    books = {
        "book1": (-3.4, -4.0),
        "book2": (-3.5, -4.1),
        "book3": (-3.6, -4.2),
        "book4": (-3.5, -4.3),
    }
    rows: list[OddsSnapshot] = []
    for book, (start_line, end_line) in books.items():
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=start_line,
                fetched_at=now - timedelta(minutes=2, seconds=30),
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=end_line,
                fetched_at=now - timedelta(seconds=30),
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    created = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=None)
    assert len(created) == 1
    signal = created[0]
    assert signal.signal_type == "STEAM"
    assert signal.market == "spreads"
    assert signal.books_affected == 4
    assert signal.metadata_json["direction"] == "down"
    assert len(signal.metadata_json["books_involved"]) == 4
    assert abs(signal.metadata_json["total_move"]) >= 0.5


async def test_steam_not_created_when_books_below_min(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_steam_low_books"
    rows: list[OddsSnapshot] = []
    for i, book in enumerate(["book1", "book2", "book3"]):
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=-3.0 - (0.1 * i),
                fetched_at=now - timedelta(minutes=2),
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=-3.7 - (0.1 * i),
                fetched_at=now - timedelta(seconds=20),
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    created = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=None)
    assert created == []


async def test_steam_not_created_for_mixed_direction_books(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_steam_mixed_direction"
    books = {
        "book1": (-3.5, -4.1),  # down
        "book2": (-3.4, -3.9),  # down
        "book3": (-3.8, -3.1),  # up
        "book4": (-3.7, -3.0),  # up
    }
    rows: list[OddsSnapshot] = []
    for book, (start_line, end_line) in books.items():
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=start_line,
                fetched_at=now - timedelta(minutes=2),
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=end_line,
                fetched_at=now - timedelta(seconds=10),
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    created = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=None)
    assert created == []


async def test_steam_not_created_below_move_threshold(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_steam_below_threshold"
    books = {
        "book1": (226.0, 225.7),
        "book2": (226.2, 225.9),
        "book3": (225.8, 225.5),
        "book4": (226.1, 225.8),
    }
    rows: list[OddsSnapshot] = []
    for book, (start_line, end_line) in books.items():
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=start_line,
                fetched_at=now - timedelta(minutes=2),
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=end_line,
                fetched_at=now - timedelta(seconds=20),
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    created = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=None)
    assert created == []


async def test_steam_dedupe_cooldown_blocks_repeat(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_steam_dedupe"
    redis = FakeRedis()

    rows: list[OddsSnapshot] = []
    for i, book in enumerate(["book1", "book2", "book3", "book4"]):
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=225.0 + (0.1 * i),
                fetched_at=now - timedelta(minutes=2, seconds=30),
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=226.2 + (0.1 * i),
                fetched_at=now - timedelta(seconds=15),
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    first = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=redis)
    second = await detect_steam_v2(event_ids=[event_id], db=db_session, redis=redis)

    assert len(first) == 1
    assert second == []
