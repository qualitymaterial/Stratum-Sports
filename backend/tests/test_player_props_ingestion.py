from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.player_prop_snapshot import PlayerPropSnapshot
from app.services.ingestion import ingest_odds_cycle, normalize_event_player_props_rows
from app.services.odds_api import OddsFetchResult


def _base_event(
    *,
    event_id: str,
    sport_key: str = "basketball_nba",
    commence_offset_hours: float = 2.0,
) -> dict:
    commence_time = (datetime.now(UTC) + timedelta(hours=commence_offset_hours)).isoformat().replace("+00:00", "Z")
    return {
        "id": event_id,
        "sport_key": sport_key,
        "commence_time": commence_time,
        "home_team": "Boston Celtics",
        "away_team": "Philadelphia 76ers",
        "bookmakers": [
            {
                "key": "book1",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Boston Celtics", "price": -130},
                            {"name": "Philadelphia 76ers", "price": 110},
                        ],
                    }
                ],
            }
        ],
    }


def _props_event(*, event_id: str) -> dict:
    event = _base_event(event_id=event_id)
    event["bookmakers"] = [
        {
            "key": "book1",
            "markets": [
                {
                    "key": "player_points",
                    "outcomes": [
                        {"name": "Over", "description": "Jayson Tatum", "price": -125, "point": 28.5},
                        {"name": "Under", "description": "Jayson Tatum", "price": 102, "point": 28.5},
                    ],
                },
                {
                    "key": "player_rebounds",
                    "outcomes": [
                        {"name": "Over", "participant": "Joel Embiid", "price": -118, "point": 10.5},
                        {"name": "Under", "participant": "Joel Embiid", "price": -104, "point": 10.5},
                    ],
                },
            ],
        }
    ]
    return event


def test_normalize_event_player_props_rows_filters_and_parses() -> None:
    event = _props_event(event_id="evt-normalize-props")
    event["bookmakers"][0]["markets"].append(
        {
            "key": "player_assists",
            "outcomes": [
                {"name": "Over", "price": -110, "point": 7.5},  # missing player identity, should be skipped
            ],
        }
    )

    rows = normalize_event_player_props_rows(
        event,
        fetched_at=datetime.now(UTC),
        allowed_markets={"player_points", "player_rebounds"},
    )
    assert len(rows) == 4
    assert rows[0].market == "player_points"
    assert rows[0].player_name == "Jayson Tatum"
    assert rows[0].outcome_name == "Over"
    assert rows[0].line == 28.5
    assert rows[2].market == "player_rebounds"
    assert rows[2].player_name == "Joel Embiid"


async def test_ingest_props_enabled_fetches_and_persists_player_prop_snapshots(db_session, monkeypatch) -> None:
    settings = get_settings()
    original_consensus = settings.consensus_enabled
    original_sports = settings.odds_api_sport_keys
    original_props_enabled = settings.player_props_ingest_enabled
    original_props_sports = settings.player_props_sport_keys
    original_props_markets = settings.player_props_markets
    original_props_max_events = settings.player_props_max_events_per_cycle
    original_props_hours = settings.player_props_commence_within_hours

    settings.consensus_enabled = False
    settings.odds_api_sport_keys = "basketball_nba"
    settings.player_props_ingest_enabled = True
    settings.player_props_sport_keys = "basketball_nba"
    settings.player_props_markets = "player_points,player_rebounds,player_assists"
    settings.player_props_max_events_per_cycle = 4
    settings.player_props_commence_within_hours = 24

    class FakeOddsApiClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def fetch_nba_odds(
            self,
            *,
            sport_key: str = "basketball_nba",
            markets: str | None = None,
            event_ids: str | None = None,
            **_kwargs,
        ) -> OddsFetchResult:
            self.calls.append(
                {
                    "sport_key": sport_key,
                    "markets": markets,
                    "event_ids": event_ids,
                }
            )
            if markets is None:
                return OddsFetchResult(
                    events=[_base_event(event_id="evt-props-live")],
                    requests_remaining=1000,
                    requests_last=1,
                    requests_limit=1200,
                )
            return OddsFetchResult(
                events=[_props_event(event_id="evt-props-live")],
                requests_remaining=999,
                requests_last=2,
                requests_limit=1200,
            )

    fake_client = FakeOddsApiClient()
    monkeypatch.setattr("app.services.ingestion.OddsApiClient", lambda: fake_client)

    try:
        result = await ingest_odds_cycle(db_session, redis=None)
    finally:
        settings.consensus_enabled = original_consensus
        settings.odds_api_sport_keys = original_sports
        settings.player_props_ingest_enabled = original_props_enabled
        settings.player_props_sport_keys = original_props_sports
        settings.player_props_markets = original_props_markets
        settings.player_props_max_events_per_cycle = original_props_max_events
        settings.player_props_commence_within_hours = original_props_hours

    assert result["player_props_enabled"] is True
    assert result["player_props_fetches"] == 1
    assert result["player_props_events_seen"] == 1
    assert result["player_props_snapshots_inserted"] == 4
    assert result["api_requests_last"] == 3
    assert len(fake_client.calls) == 2
    assert fake_client.calls[1]["markets"] == "player_points,player_rebounds,player_assists"
    assert fake_client.calls[1]["event_ids"] == "evt-props-live"

    count_stmt = select(func.count(PlayerPropSnapshot.id)).where(PlayerPropSnapshot.event_id == "evt-props-live")
    assert (await db_session.execute(count_stmt)).scalar_one() == 4


async def test_ingest_props_skipped_for_live_watchlist_mode(db_session, monkeypatch) -> None:
    settings = get_settings()
    original_consensus = settings.consensus_enabled
    original_sports = settings.odds_api_sport_keys
    original_props_enabled = settings.player_props_ingest_enabled
    original_props_sports = settings.player_props_sport_keys
    original_props_markets = settings.player_props_markets

    settings.consensus_enabled = False
    settings.odds_api_sport_keys = "basketball_nba"
    settings.player_props_ingest_enabled = True
    settings.player_props_sport_keys = "basketball_nba"
    settings.player_props_markets = "player_points,player_rebounds,player_assists"

    class FakeOddsApiClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def fetch_nba_odds(
            self,
            *,
            sport_key: str = "basketball_nba",
            markets: str | None = None,
            event_ids: str | None = None,
            **_kwargs,
        ) -> OddsFetchResult:
            self.calls.append(
                {
                    "sport_key": sport_key,
                    "markets": markets,
                    "event_ids": event_ids,
                }
            )
            return OddsFetchResult(
                events=[_base_event(event_id="evt-watchlist-live")],
                requests_remaining=900,
                requests_last=1,
                requests_limit=1200,
            )

    fake_client = FakeOddsApiClient()
    monkeypatch.setattr("app.services.ingestion.OddsApiClient", lambda: fake_client)

    try:
        result = await ingest_odds_cycle(
            db_session,
            redis=None,
            eligible_event_ids={"evt-watchlist-live"},
            sport_event_ids={"basketball_nba": ["evt-watchlist-live"]},
        )
    finally:
        settings.consensus_enabled = original_consensus
        settings.odds_api_sport_keys = original_sports
        settings.player_props_ingest_enabled = original_props_enabled
        settings.player_props_sport_keys = original_props_sports
        settings.player_props_markets = original_props_markets

    assert result["player_props_enabled"] is True
    assert result["player_props_fetches"] == 0
    assert result["player_props_events_seen"] == 0
    assert result["player_props_snapshots_inserted"] == 0
    assert len(fake_client.calls) == 1
