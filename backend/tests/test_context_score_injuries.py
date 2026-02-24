from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.services.context_score import injuries as injuries_service


def _game(event_id: str, commence_time: datetime) -> Game:
    return Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="Boston Celtics",
        away_team="New York Knicks",
    )


def _spread_snapshot(
    *,
    event_id: str,
    line: float,
    fetched_at: datetime,
    sportsbook_key: str,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=fetched_at + timedelta(hours=2),
        home_team="Boston Celtics",
        away_team="New York Knicks",
        sportsbook_key=sportsbook_key,
        market="spreads",
        outcome_name="Boston Celtics",
        line=line,
        price=-110,
        fetched_at=fetched_at,
    )


async def test_injury_context_uses_heuristic_by_default(db_session: AsyncSession, monkeypatch) -> None:
    now = datetime.now(UTC)
    event_id = "injury_ctx_heuristic_default"
    db_session.add(_game(event_id, now + timedelta(hours=2)))
    db_session.add_all(
        [
            _spread_snapshot(event_id=event_id, line=-3.0, fetched_at=now - timedelta(minutes=28), sportsbook_key="book1"),
            _spread_snapshot(event_id=event_id, line=-3.5, fetched_at=now - timedelta(minutes=20), sportsbook_key="book2"),
            _spread_snapshot(event_id=event_id, line=-4.0, fetched_at=now - timedelta(minutes=10), sportsbook_key="book3"),
            _spread_snapshot(event_id=event_id, line=-4.5, fetched_at=now - timedelta(minutes=2), sportsbook_key="book4"),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(injuries_service.settings, "injury_feed_provider", "heuristic")
    result = await injuries_service.get_injury_context(db_session, event_id)

    assert result["status"] == "computed"
    assert result["details"]["source"] == "heuristic"
    assert result["score"] is not None


async def test_injury_context_uses_sportsdataio_when_available(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    event_id = "injury_ctx_live_feed"
    db_session.add(_game(event_id, now + timedelta(hours=2)))
    await db_session.commit()

    monkeypatch.setattr(injuries_service.settings, "injury_feed_provider", "sportsdataio")
    monkeypatch.setattr(injuries_service.settings, "sportsdataio_api_key", "test-key")

    async def _fake_live_context(_game_obj: Game) -> dict:
        return {
            "event_id": event_id,
            "component": "injuries",
            "status": "computed",
            "score": 77,
            "details": {
                "source": "sportsdataio",
                "players_flagged": 3,
                "home_players_flagged": 2,
                "away_players_flagged": 1,
                "weighted_injury_load": 2.4,
            },
            "notes": "Derived from SportsDataIO injury statuses for teams in this matchup.",
        }

    monkeypatch.setattr(injuries_service, "get_sportsdataio_injury_context", _fake_live_context)

    result = await injuries_service.get_injury_context(db_session, event_id)
    assert result["status"] == "computed"
    assert result["details"]["source"] == "sportsdataio"
    assert result["score"] == 77


async def test_injury_context_falls_back_when_live_feed_unavailable(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    event_id = "injury_ctx_live_fallback"
    db_session.add(_game(event_id, now + timedelta(hours=2)))
    db_session.add_all(
        [
            _spread_snapshot(event_id=event_id, line=-2.5, fetched_at=now - timedelta(minutes=25), sportsbook_key="book1"),
            _spread_snapshot(event_id=event_id, line=-3.0, fetched_at=now - timedelta(minutes=17), sportsbook_key="book2"),
            _spread_snapshot(event_id=event_id, line=-3.5, fetched_at=now - timedelta(minutes=8), sportsbook_key="book3"),
            _spread_snapshot(event_id=event_id, line=-4.0, fetched_at=now - timedelta(minutes=1), sportsbook_key="book4"),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(injuries_service.settings, "injury_feed_provider", "sportsdataio")
    monkeypatch.setattr(injuries_service.settings, "sportsdataio_api_key", "test-key")

    async def _fake_none(_game_obj: Game) -> None:
        return None

    monkeypatch.setattr(injuries_service, "get_sportsdataio_injury_context", _fake_none)

    result = await injuries_service.get_injury_context(db_session, event_id)
    assert result["status"] == "computed"
    assert result["details"]["source"] == "heuristic"
    assert "sportsdataio_unavailable" in result["notes"]
