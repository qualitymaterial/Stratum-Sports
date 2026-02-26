from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.closing_consensus import ClosingConsensus
from app.models.clv_record import ClvRecord
from app.models.game import Game
from app.models.signal import Signal
from app.services.clv import compute_and_persist_clv
from app.services.historical_backfill import backfill_missing_closing_consensus


def _game(event_id: str, commence_time: datetime) -> Game:
    return Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="BOS",
        away_team="NYK",
    )


def _signal(event_id: str, commence_time: datetime) -> Signal:
    return Signal(
        event_id=event_id,
        market="spreads",
        signal_type="DISLOCATION",
        direction="DOWN",
        from_value=-3.0,
        to_value=-3.5,
        from_price=-110,
        to_price=-110,
        window_minutes=10,
        books_affected=2,
        velocity_minutes=3.0,
        strength_score=72,
        created_at=commence_time - timedelta(minutes=30),
        metadata_json={
            "outcome_name": "BOS",
            "book_line": -3.5,
            "book_price": -108.0,
        },
    )


def _history_event(event_id: str, commence_time: datetime, home_line: float) -> dict:
    return {
        "id": event_id,
        "sport_key": "basketball_nba",
        "commence_time": commence_time.isoformat().replace("+00:00", "Z"),
        "home_team": "BOS",
        "away_team": "NYK",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "BOS", "price": -110, "point": home_line},
                            {"name": "NYK", "price": -110, "point": -home_line},
                        ],
                    }
                ],
            }
        ],
    }


async def test_backfill_persists_close_using_last_snapshot_before_tipoff(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    commence_time = datetime.now(UTC) - timedelta(hours=6)
    event_id = "event_hist_backfill_pre_tipoff"
    db_session.add(_game(event_id, commence_time))
    db_session.add(_signal(event_id, commence_time))
    await db_session.commit()

    async def fake_fetch_nba_odds_history(**kwargs) -> dict:  # noqa: ANN003
        date: datetime = kwargs["date"]
        if date <= commence_time - timedelta(minutes=10):
            line = -3.0
        elif date <= commence_time:
            line = -3.5
        else:
            line = -4.0
        return {
            "events": [_history_event(event_id, commence_time, line)],
            "history_timestamp": date,
            "previous_timestamp": None,
            "next_timestamp": None,
            "requests_remaining": 1000,
            "requests_used": 1,
            "requests_last": 1,
            "requests_limit": 20000,
        }

    monkeypatch.setattr(
        "app.services.historical_backfill.fetch_nba_odds_history",
        fake_fetch_nba_odds_history,
    )

    settings = get_settings()
    metrics = await backfill_missing_closing_consensus(
        lookback_hours=72,
        max_games=5,
        settings=settings,
        db=db_session,
    )

    assert metrics["games_backfilled"] == 1
    close_row = (
        await db_session.execute(
            select(ClosingConsensus).where(
                ClosingConsensus.event_id == event_id,
                ClosingConsensus.market == "spreads",
                ClosingConsensus.outcome_name == "BOS",
            )
        )
    ).scalar_one()
    assert close_row.close_line == -3.5
    assert close_row.close_fetched_at <= commence_time


async def test_backfill_uses_earliest_post_tipoff_snapshot_when_pre_tipoff_missing(
    db_session: AsyncSession,
    monkeypatch,
    caplog,
) -> None:
    commence_time = datetime.now(UTC) - timedelta(hours=6)
    event_id = "event_hist_backfill_post_tipoff"
    db_session.add(_game(event_id, commence_time))
    db_session.add(_signal(event_id, commence_time))
    await db_session.commit()

    async def fake_fetch_nba_odds_history(**kwargs) -> dict:  # noqa: ANN003
        date: datetime = kwargs["date"]
        if date <= commence_time:
            return {
                "events": [],
                "history_timestamp": date,
                "previous_timestamp": None,
                "next_timestamp": None,
                "requests_remaining": 1000,
                "requests_used": 1,
                "requests_last": 1,
                "requests_limit": 20000,
            }
        return {
            "events": [_history_event(event_id, commence_time, -2.5)],
            "history_timestamp": date,
            "previous_timestamp": None,
            "next_timestamp": None,
            "requests_remaining": 1000,
            "requests_used": 1,
            "requests_last": 1,
            "requests_limit": 20000,
        }

    monkeypatch.setattr(
        "app.services.historical_backfill.fetch_nba_odds_history",
        fake_fetch_nba_odds_history,
    )

    caplog.set_level(logging.WARNING, logger="app.services.historical_backfill")
    settings = get_settings()
    metrics = await backfill_missing_closing_consensus(
        lookback_hours=72,
        max_games=5,
        settings=settings,
        db=db_session,
    )

    assert metrics["games_backfilled"] == 1
    close_row = (
        await db_session.execute(
            select(ClosingConsensus).where(
                ClosingConsensus.event_id == event_id,
                ClosingConsensus.market == "spreads",
                ClosingConsensus.outcome_name == "BOS",
            )
        )
    ).scalar_one()
    assert close_row.close_fetched_at > commence_time
    assert any("inferred close from post-tipoff snapshot" in record.message for record in caplog.records)


async def test_compute_clv_skips_missing_close_and_persists_when_close_exists(
    db_session: AsyncSession,
) -> None:
    commence_time = datetime.now(UTC) - timedelta(hours=6)
    event_without_close = "event_clv_missing_close"
    event_with_close = "event_clv_has_close"

    db_session.add_all(
        [
            _game(event_without_close, commence_time),
            _game(event_with_close, commence_time),
            _signal(event_without_close, commence_time),
            _signal(event_with_close, commence_time),
            ClosingConsensus(
                event_id=event_with_close,
                market="spreads",
                outcome_name="BOS",
                close_line=-4.0,
                close_price=-110.0,
                close_fetched_at=commence_time - timedelta(minutes=1),
                computed_at=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    inserted = await compute_and_persist_clv(db_session, days_lookback=7)
    assert inserted == 1

    clv_rows = (await db_session.execute(select(ClvRecord))).scalars().all()
    assert len(clv_rows) == 1
    assert clv_rows[0].event_id == event_with_close
