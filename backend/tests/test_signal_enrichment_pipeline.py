from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.services.signals import detect_market_movements


def _snapshot(
    *,
    event_id: str,
    commence_time: datetime,
    sportsbook_key: str,
    outcome_name: str,
    line: float,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="Home Team",
        away_team="Away Team",
        sportsbook_key=sportsbook_key,
        market="spreads",
        outcome_name=outcome_name,
        line=line,
        price=-110,
        fetched_at=fetched_at,
    )


async def test_detect_market_movements_enriches_move_family_only(db_session) -> None:
    now = datetime.now(UTC)
    event_id = "event_signal_enrichment"
    commence_time = now + timedelta(hours=2)

    db_session.add(
        Game(
            event_id=event_id,
            sport_key="basketball_nba",
            commence_time=commence_time,
            home_team="Home Team",
            away_team="Away Team",
        )
    )

    t0 = now - timedelta(minutes=4)
    t1 = now - timedelta(minutes=1)
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book1",
                outcome_name="Home Team",
                line=-2.9,
                fetched_at=t0,
            ),
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book1",
                outcome_name="Home Team",
                line=-3.3,
                fetched_at=t1,
            ),
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book2",
                outcome_name="Home Team",
                line=-3.0,
                fetched_at=t0,
            ),
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book2",
                outcome_name="Home Team",
                line=-3.4,
                fetched_at=t1,
            ),
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book3",
                outcome_name="Home Team",
                line=-2.8,
                fetched_at=t0,
            ),
            _snapshot(
                event_id=event_id,
                commence_time=commence_time,
                sportsbook_key="book3",
                outcome_name="Home Team",
                line=-3.2,
                fetched_at=t1,
            ),
        ]
    )
    await db_session.commit()

    await detect_market_movements(db_session, redis=None, event_ids=[event_id])

    signals = (
        (
            await db_session.execute(
                select(Signal).where(Signal.event_id == event_id).order_by(Signal.created_at.desc(), Signal.id.desc())
            )
        )
        .scalars()
        .all()
    )
    assert signals

    move_family = [signal for signal in signals if signal.signal_type in {"MOVE", "KEY_CROSS"}]
    assert move_family
    for signal in move_family:
        assert signal.velocity is not None
        assert signal.minutes_to_tip is not None
        assert signal.time_bucket is not None
        assert signal.composite_score is not None
        assert signal.computed_at is not None
        assert 0 <= int(signal.composite_score) <= 100

    multibook = next((signal for signal in signals if signal.signal_type == "MULTIBOOK_SYNC"), None)
    assert multibook is not None
    assert multibook.velocity is None
    assert multibook.acceleration is None
    assert multibook.time_bucket is None
    assert multibook.composite_score is None
    assert multibook.minutes_to_tip is None
    assert multibook.computed_at is None
