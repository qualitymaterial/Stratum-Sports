from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.services.signals import detect_dislocations


class FakeRedis:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._keys:
            return None
        self._keys[key] = value
        return True


def _consensus(
    *,
    event_id: str,
    market: str,
    outcome_name: str,
    consensus_line: float | None,
    consensus_price: float | None,
    books_count: int,
    dispersion: float | None,
    fetched_at: datetime,
) -> MarketConsensusSnapshot:
    return MarketConsensusSnapshot(
        event_id=event_id,
        market=market,
        outcome_name=outcome_name,
        consensus_line=consensus_line,
        consensus_price=consensus_price,
        dispersion=dispersion,
        books_count=books_count,
        fetched_at=fetched_at,
    )


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    market: str,
    outcome_name: str,
    line: float | None,
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
        market=market,
        outcome_name=outcome_name,
        line=line,
        price=price,
        fetched_at=fetched_at,
    )


async def test_dislocation_spread_creates_signal_for_outlier_only(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_dislocation_spread"

    db_session.add(
        _consensus(
            event_id=event_id,
            market="spreads",
            outcome_name="BOS",
            consensus_line=-4.0,
            consensus_price=-110.0,
            books_count=6,
            dispersion=0.3,
            fetched_at=now - timedelta(minutes=1),
        )
    )

    lines = [-4.1, -4.4, -3.8, -4.0, -3.5, -2.7]
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key=f"book{i + 1}",
                market="spreads",
                outcome_name="BOS",
                line=line,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            )
            for i, line in enumerate(lines)
        ]
    )
    await db_session.commit()

    created = await detect_dislocations(event_ids=[event_id], db=db_session, redis=None)
    assert len(created) == 1

    signal = created[0]
    assert signal.signal_type == "DISLOCATION"
    assert signal.market == "spreads"
    assert signal.metadata_json["book_key"] == "book6"
    assert signal.metadata_json["delta_type"] == "line"
    assert abs(signal.metadata_json["delta"] - 1.3) < 0.001


async def test_dislocation_skips_when_consensus_missing_or_books_too_low(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_missing = "event_dislocation_missing_consensus"
    event_low = "event_dislocation_low_books"

    db_session.add(
        _snapshot(
            event_id=event_missing,
            sportsbook_key="book1",
            market="spreads",
            outcome_name="BOS",
            line=-1.5,
            price=-110,
            fetched_at=now - timedelta(minutes=1),
        )
    )

    db_session.add(
        _consensus(
            event_id=event_low,
            market="spreads",
            outcome_name="BOS",
            consensus_line=-4.0,
            consensus_price=-110.0,
            books_count=4,
            dispersion=0.2,
            fetched_at=now - timedelta(minutes=1),
        )
    )
    db_session.add(
        _snapshot(
            event_id=event_low,
            sportsbook_key="book1",
            market="spreads",
            outcome_name="BOS",
            line=-2.0,
            price=-110,
            fetched_at=now - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    created = await detect_dislocations(
        event_ids=[event_missing, event_low],
        db=db_session,
        redis=None,
    )
    assert created == []


async def test_dislocation_h2h_uses_implied_probability_delta(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_dislocation_h2h"

    db_session.add(
        _consensus(
            event_id=event_id,
            market="h2h",
            outcome_name="BOS",
            consensus_line=None,
            consensus_price=-120.0,
            books_count=6,
            dispersion=0.01,
            fetched_at=now - timedelta(minutes=1),
        )
    )

    prices = [-121, -119, -118, -117, 120]
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key=f"book{i + 1}",
                market="h2h",
                outcome_name="BOS",
                line=None,
                price=price,
                fetched_at=now - timedelta(minutes=1),
            )
            for i, price in enumerate(prices)
        ]
    )
    await db_session.commit()

    created = await detect_dislocations(event_ids=[event_id], db=db_session, redis=None)
    assert len(created) == 1

    signal = created[0]
    assert signal.signal_type == "DISLOCATION"
    assert signal.market == "h2h"
    assert signal.metadata_json["delta_type"] == "implied_prob"
    assert signal.metadata_json["book_key"] == "book5"
    assert abs(signal.metadata_json["delta"]) >= 0.03


async def test_dislocation_redis_cooldown_dedupes_repeats(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_dislocation_cooldown"
    redis = FakeRedis()

    db_session.add(
        _consensus(
            event_id=event_id,
            market="totals",
            outcome_name="Over",
            consensus_line=226.0,
            consensus_price=-110.0,
            books_count=6,
            dispersion=0.5,
            fetched_at=now - timedelta(minutes=1),
        )
    )
    db_session.add(
        _snapshot(
            event_id=event_id,
            sportsbook_key="book1",
            market="totals",
            outcome_name="Over",
            line=223.5,
            price=-110,
            fetched_at=now - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    first = await detect_dislocations(event_ids=[event_id], db=db_session, redis=redis)
    second = await detect_dislocations(event_ids=[event_id], db=db_session, redis=redis)

    assert len(first) == 1
    assert second == []
