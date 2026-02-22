from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.services.odds_api import HistoryProbeResult, OddsFetchResult
from app.tools.backfill_history import BackfillConfig, run_history_backfill


def _event_payload(event_id: str, commence_time: str) -> dict:
    return {
        "id": event_id,
        "sport_key": "basketball_nba",
        "commence_time": commence_time,
        "home_team": "Boston Celtics",
        "away_team": "New York Knicks",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Boston Celtics", "price": -110, "point": -3.5},
                            {"name": "New York Knicks", "price": -110, "point": 3.5},
                        ],
                    }
                ],
            }
        ],
    }


class FakeOddsClient:
    def __init__(
        self,
        *,
        bulk_probe_status: int = 200,
        bulk_probe_events: int = 1,
        event_probe_status: int = 200,
        event_probe_events: int = 1,
    ) -> None:
        self.history_calls: list[tuple[str, str | None, datetime]] = []
        self.bulk_probe_status = bulk_probe_status
        self.bulk_probe_events = bulk_probe_events
        self.event_probe_status = event_probe_status
        self.event_probe_events = event_probe_events

    async def fetch_nba_odds(self, **kwargs) -> OddsFetchResult:  # noqa: ANN003
        return OddsFetchResult(
            events=[
                {
                    "id": "evt_backfill_1",
                    "sport_key": "basketball_nba",
                    "commence_time": "2026-02-21T00:30:00Z",
                    "home_team": "Boston Celtics",
                    "away_team": "New York Knicks",
                    "bookmakers": [],
                }
            ],
            requests_last=1,
            requests_remaining=500,
            requests_limit=20000,
        )

    async def probe_nba_odds_history(self, **kwargs) -> HistoryProbeResult:  # noqa: ANN003
        endpoint_variant: str = kwargs["endpoint_variant"]
        if endpoint_variant == "bulk":
            return HistoryProbeResult(
                endpoint_variant="bulk",
                status_code=self.bulk_probe_status,
                body_preview='{"ok":true,"variant":"bulk"}',
                events_found=self.bulk_probe_events,
                requests_remaining=498,
                requests_last=1,
                requests_limit=20000,
            )
        return HistoryProbeResult(
            endpoint_variant="event",
            status_code=self.event_probe_status,
            body_preview='{"ok":true,"variant":"event"}',
            events_found=self.event_probe_events,
            requests_remaining=497,
            requests_last=1,
            requests_limit=20000,
        )

    async def fetch_nba_odds_history(self, **kwargs) -> OddsFetchResult:  # noqa: ANN003
        date: datetime = kwargs["date"]
        endpoint_variant: str = kwargs["endpoint_variant"]
        event_id: str | None = kwargs.get("event_id")
        self.history_calls.append((endpoint_variant, event_id, date))
        event = _event_payload("evt_backfill_1", "2026-02-21T00:30:00Z")
        if date.hour == 0:
            event["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = -3.5
            event["bookmakers"][0]["markets"][0]["outcomes"][1]["point"] = 3.5
        else:
            event["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = -4.0
            event["bookmakers"][0]["markets"][0]["outcomes"][1]["point"] = 4.0

        return OddsFetchResult(
            events=[event],
            requests_last=1,
            requests_remaining=500 - len(self.history_calls),
            requests_limit=20000,
            history_timestamp=date,
        )


class BudgetStopClient(FakeOddsClient):
    async def fetch_nba_odds(self, **kwargs) -> OddsFetchResult:  # noqa: ANN003
        result = await super().fetch_nba_odds(**kwargs)
        return OddsFetchResult(
            events=result.events,
            requests_last=1,
            requests_remaining=100,
            requests_limit=20000,
        )


async def test_backfill_history_idempotent_and_games_upserted(db_session: AsyncSession) -> None:
    client = FakeOddsClient()
    config = BackfillConfig(
        start=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 21, 1, 0, tzinfo=UTC),
        sport_key="basketball_nba",
        markets=("spreads", "totals", "h2h"),
        max_events=10,
        max_requests=200,
        min_requests_remaining=50,
        history_step_minutes=60,
    )

    first = await run_history_backfill(db_session, config=config, client=client)
    second = await run_history_backfill(db_session, config=config, client=client)

    assert first["events_processed"] == 1
    assert first["snapshots_inserted"] == 8
    assert first["duplicates_skipped"] == 0
    assert first["budget_stopped"] is False
    assert first["history_endpoint_variant"] == "bulk"
    assert first["api_requests_used"] == 5  # 1 current odds + 4 history calls (tip-aware)
    assert first["probe_requests_used"] == 2
    assert first["total_http_calls"] == 7
    assert first["earliest_fetched_at"] == "2026-02-21T00:00:00+00:00"
    assert first["latest_fetched_at"] == "2026-02-21T01:00:00+00:00"

    assert second["events_processed"] == 1
    assert second["snapshots_inserted"] == 0
    assert second["duplicates_skipped"] == 8
    assert second["api_requests_used"] == 5
    assert second["probe_requests_used"] == 2
    assert second["total_http_calls"] == 7

    game = (await db_session.execute(select(Game).where(Game.event_id == "evt_backfill_1"))).scalar_one_or_none()
    assert game is not None

    snapshot_count = (
        await db_session.execute(select(OddsSnapshot).where(OddsSnapshot.event_id == "evt_backfill_1"))
    ).scalars().all()
    assert len(snapshot_count) == 8


async def test_backfill_history_budget_stop(db_session: AsyncSession) -> None:
    client = BudgetStopClient()
    config = BackfillConfig(
        start=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 21, 1, 0, tzinfo=UTC),
        sport_key="basketball_nba",
        markets=("spreads", "totals", "h2h"),
        max_events=10,
        max_requests=1,
        min_requests_remaining=50,
        history_step_minutes=60,
    )

    summary = await run_history_backfill(db_session, config=config, client=client)

    assert summary["budget_stopped"] is True
    assert summary["budget_stop_reason"] == "max_requests_reached"
    assert summary["events_processed"] == 0
    assert summary["snapshots_inserted"] == 0
    assert summary["api_requests_used"] == 1
    assert summary["probe_requests_used"] == 0
    assert summary["total_http_calls"] == 1
    assert len(client.history_calls) == 0


async def test_backfill_prefers_bulk_history_endpoint(db_session: AsyncSession) -> None:
    client = FakeOddsClient(
        bulk_probe_status=200,
        bulk_probe_events=2,
        event_probe_status=200,
        event_probe_events=1,
    )
    config = BackfillConfig(
        start=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 21, 0, 31, tzinfo=UTC),
        sport_key="basketball_nba",
        markets=("spreads", "totals"),
        max_events=1,
        max_requests=50,
        min_requests_remaining=10,
        history_step_minutes=60,
    )

    summary = await run_history_backfill(db_session, config=config, client=client)

    assert summary["history_endpoint_variant"] == "bulk"
    assert summary["snapshots_inserted"] == 6
    assert client.history_calls
    assert all(call[0] == "bulk" for call in client.history_calls)


async def test_backfill_falls_back_to_event_history_endpoint(db_session: AsyncSession) -> None:
    client = FakeOddsClient(
        bulk_probe_status=404,
        bulk_probe_events=0,
        event_probe_status=200,
        event_probe_events=1,
    )
    config = BackfillConfig(
        start=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 21, 0, 31, tzinfo=UTC),
        sport_key="basketball_nba",
        markets=("spreads",),
        max_events=1,
        max_requests=50,
        min_requests_remaining=10,
        history_step_minutes=60,
    )

    summary = await run_history_backfill(db_session, config=config, client=client)

    assert summary["history_endpoint_variant"] == "event"
    assert summary["snapshots_inserted"] == 6
    assert client.history_calls
    assert all(call[0] == "event" for call in client.history_calls)
