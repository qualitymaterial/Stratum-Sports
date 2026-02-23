from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.models.game import Game
from app.services.ingestion import ingest_odds_cycle
from app.services.odds_api import OddsFetchResult


def _event_payload(*, event_id: str, sport_key: str, home_team: str, away_team: str) -> dict:
    commence_time = (datetime.now(UTC) + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    return {
        "id": event_id,
        "sport_key": sport_key,
        "commence_time": commence_time,
        "home_team": home_team,
        "away_team": away_team,
        "bookmakers": [
            {
                "key": "book1",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": home_team, "price": -120},
                            {"name": away_team, "price": 110},
                        ],
                    }
                ],
            }
        ],
    }


async def test_ingest_odds_cycle_polls_multiple_sports_and_aggregates_headers(
    db_session,
    monkeypatch,
) -> None:
    settings = get_settings()
    original_sports = settings.odds_api_sport_keys
    original_consensus = settings.consensus_enabled

    settings.odds_api_sport_keys = "basketball_nba,americanfootball_nfl"
    settings.consensus_enabled = False

    class FakeOddsApiClient:
        async def fetch_nba_odds(self, *, sport_key: str = "basketball_nba", **_kwargs) -> OddsFetchResult:
            if sport_key == "basketball_nba":
                return OddsFetchResult(
                    events=[
                        _event_payload(
                            event_id="evt_nba_1",
                            sport_key=sport_key,
                            home_team="Boston Celtics",
                            away_team="Miami Heat",
                        )
                    ],
                    requests_remaining=900,
                    requests_used=100,
                    requests_last=1,
                    requests_limit=1200,
                )
            if sport_key == "americanfootball_nfl":
                return OddsFetchResult(
                    events=[
                        _event_payload(
                            event_id="evt_nfl_1",
                            sport_key=sport_key,
                            home_team="Kansas City Chiefs",
                            away_team="Buffalo Bills",
                        )
                    ],
                    requests_remaining=880,
                    requests_used=101,
                    requests_last=2,
                    requests_limit=1200,
                )
            return OddsFetchResult(events=[])

    monkeypatch.setattr("app.services.ingestion.OddsApiClient", lambda: FakeOddsApiClient())

    try:
        result = await ingest_odds_cycle(db_session, redis=None)
    finally:
        settings.odds_api_sport_keys = original_sports
        settings.consensus_enabled = original_consensus

    assert result["events_seen"] == 2
    assert result["events_processed"] == 2
    assert result["api_requests_last"] == 3
    assert result["api_requests_remaining"] == 880
    assert result["api_requests_limit"] == 1200
    assert result["sports_polled"] == ["basketball_nba", "americanfootball_nfl"]
    assert result["events_seen_by_sport"] == {"basketball_nba": 1, "americanfootball_nfl": 1}

    games = (await db_session.execute(select(Game.event_id, Game.sport_key))).all()
    assert set(games) == {
        ("evt_nba_1", "basketball_nba"),
        ("evt_nfl_1", "americanfootball_nfl"),
    }


async def test_ingest_odds_cycle_respects_eligible_event_ids_across_sports(
    db_session,
    monkeypatch,
) -> None:
    settings = get_settings()
    original_sports = settings.odds_api_sport_keys
    original_consensus = settings.consensus_enabled

    settings.odds_api_sport_keys = "basketball_nba,americanfootball_nfl"
    settings.consensus_enabled = False

    class FakeOddsApiClient:
        async def fetch_nba_odds(self, *, sport_key: str = "basketball_nba", **_kwargs) -> OddsFetchResult:
            return OddsFetchResult(
                events=[
                    _event_payload(
                        event_id=f"evt_{sport_key}",
                        sport_key=sport_key,
                        home_team=f"{sport_key}_home",
                        away_team=f"{sport_key}_away",
                    )
                ],
                requests_remaining=800,
                requests_last=1,
                requests_limit=1200,
            )

    monkeypatch.setattr("app.services.ingestion.OddsApiClient", lambda: FakeOddsApiClient())

    try:
        result = await ingest_odds_cycle(
            db_session,
            redis=None,
            eligible_event_ids={"evt_basketball_nba"},
        )
    finally:
        settings.odds_api_sport_keys = original_sports
        settings.consensus_enabled = original_consensus

    assert result["events_seen"] == 1
    assert result["events_processed"] == 1
    assert result["event_ids"] == ["evt_basketball_nba"]
    assert result["event_ids_updated"] == ["evt_basketball_nba"]

