from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clv_record import ClvRecord
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.models.teaser_interaction_event import TeaserInteractionEvent
from app.models.user import User
from app.services import performance_intel


def _signal(
    *,
    event_id: str,
    market: str,
    signal_type: str,
    strength: int,
    created_at: datetime,
    metadata: dict,
    velocity: float | None = None,
    acceleration: float | None = None,
    time_bucket: str | None = None,
    composite_score: int | None = None,
    minutes_to_tip: int | None = None,
    computed_at: datetime | None = None,
) -> Signal:
    return Signal(
        event_id=event_id,
        market=market,
        signal_type=signal_type,
        direction="UP",
        from_value=-3.0,
        to_value=-2.5,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=3,
        velocity_minutes=3.0,
        velocity=velocity,
        acceleration=acceleration,
        time_bucket=time_bucket,
        composite_score=composite_score,
        minutes_to_tip=minutes_to_tip,
        computed_at=computed_at,
        strength_score=strength,
        created_at=created_at,
        metadata_json=metadata,
    )


def _snapshot(
    *,
    event_id: str,
    market: str,
    outcome_name: str,
    sportsbook_key: str,
    line: float | None,
    price: int,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=fetched_at + timedelta(hours=1),
        home_team="BOS",
        away_team="NYK",
        sportsbook_key=sportsbook_key,
        market=market,
        outcome_name=outcome_name,
        line=line,
        price=price,
        fetched_at=fetched_at,
    )


def _game(*, event_id: str, commence_time: datetime, sport_key: str = "basketball_nba") -> Game:
    return Game(
        event_id=event_id,
        sport_key=sport_key,
        commence_time=commence_time,
        home_team="BOS",
        away_team="NYK",
    )


async def _seed_public_teaser_signal(
    db_session: AsyncSession,
    *,
    event_id: str,
    sport_key: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    created_at: datetime,
    strength: int = 90,
    quote_fetched_at: datetime | None = None,
) -> None:
    if quote_fetched_at is None:
        quote_fetched_at = datetime.now(UTC) - timedelta(minutes=1)
    game = Game(
        event_id=event_id,
        sport_key=sport_key,
        commence_time=commence_time,
        home_team=home_team,
        away_team=away_team,
    )
    signal = _signal(
        event_id=event_id,
        market="spreads",
        signal_type="MOVE",
        strength=strength,
        created_at=created_at,
        metadata={"outcome_name": home_team},
    )
    db_session.add_all([game, signal])
    await db_session.flush()

    db_session.add_all(
        [
            OddsSnapshot(
                event_id=event_id,
                sport_key=sport_key,
                commence_time=commence_time,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="draftkings",
                market="spreads",
                outcome_name=home_team,
                line=-2.5,
                price=-110,
                fetched_at=quote_fetched_at,
            ),
            OddsSnapshot(
                event_id=event_id,
                sport_key=sport_key,
                commence_time=commence_time,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="fanduel",
                market="spreads",
                outcome_name=home_team,
                line=-3.0,
                price=-108,
                fetched_at=quote_fetched_at,
            ),
        ]
    )

async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "PerfPass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _register_pro_user(async_client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    token = await _register(async_client, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.tier = "pro"
    await db_session.commit()
    return token


async def _ensure_teaser_events_table(db_session: AsyncSession) -> None:
    await db_session.run_sync(
        lambda sync_session: TeaserInteractionEvent.__table__.create(
            bind=sync_session.connection(),
            checkfirst=True,
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/intel/clv?days=7",
        "/api/v1/intel/clv/summary?days=7",
        "/api/v1/intel/clv/recap?days=7&grain=day",
        "/api/v1/intel/clv/scorecards?days=7",
        "/api/v1/intel/clv/teaser?days=7",
        "/api/v1/intel/opportunities/teaser?days=7",
        "/api/v1/intel/signals/quality?days=7",
        "/api/v1/intel/signals/weekly-summary?days=7",
        "/api/v1/intel/signals/lifecycle?days=7",
    ],
)
async def test_intel_endpoints_reject_invalid_sport_key(
    async_client: AsyncClient,
    db_session: AsyncSession,
    path: str,
) -> None:
    token = await _register_pro_user(async_client, db_session, "perf-invalid-sport@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(f"{path}&sport_key=invalid_sport", headers=headers)
    assert response.status_code == 400
    assert "Unsupported sport_key" in response.json()["detail"]


async def test_clv_summary_endpoint_supports_filters(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_clv_summary"

    move_signal = _signal(
        event_id=event_id,
        market="spreads",
        signal_type="MOVE",
        strength=85,
        created_at=now - timedelta(days=2),
        metadata={"outcome_name": "BOS"},
    )
    dislocation_signal = _signal(
        event_id=event_id,
        market="totals",
        signal_type="DISLOCATION",
        strength=55,
        created_at=now - timedelta(days=1),
        metadata={"outcome_name": "Over", "dispersion": 1.2},
    )
    db_session.add_all([move_signal, dislocation_signal])
    await db_session.flush()

    db_session.add_all(
        [
            ClvRecord(
                signal_id=move_signal.id,
                event_id=event_id,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.0,
                entry_price=None,
                close_line=-3.5,
                close_price=None,
                clv_line=-0.5,
                clv_prob=None,
                computed_at=now - timedelta(days=2),
            ),
            ClvRecord(
                signal_id=dislocation_signal.id,
                event_id=event_id,
                signal_type="DISLOCATION",
                market="totals",
                outcome_name="Over",
                entry_line=220.0,
                entry_price=None,
                close_line=221.5,
                close_price=None,
                clv_line=1.5,
                clv_prob=None,
                computed_at=now - timedelta(days=1),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-summary@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.get(
        "/api/v1/intel/clv/summary?days=30&signal_type=MOVE&market=spreads&min_samples=1&min_strength=80",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["signal_type"] == "MOVE"
    assert payload[0]["market"] == "spreads"
    assert payload[0]["count"] == 1


async def test_clv_summary_endpoint_filters_by_sport_key(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)

    nba_event = "event_perf_clv_summary_nba"
    ncaab_event = "event_perf_clv_summary_ncaab"
    db_session.add_all(
        [
            _game(event_id=nba_event, commence_time=now - timedelta(hours=4), sport_key="basketball_nba"),
            _game(event_id=ncaab_event, commence_time=now - timedelta(hours=5), sport_key="basketball_ncaab"),
        ]
    )

    nba_signal = _signal(
        event_id=nba_event,
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(days=2),
        metadata={"outcome_name": "BOS"},
    )
    ncaab_signal = _signal(
        event_id=ncaab_event,
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(days=2),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all([nba_signal, ncaab_signal])
    await db_session.flush()

    db_session.add_all(
        [
            ClvRecord(
                signal_id=nba_signal.id,
                event_id=nba_event,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.0,
                entry_price=None,
                close_line=-3.5,
                close_price=None,
                clv_line=-0.5,
                clv_prob=None,
                computed_at=now - timedelta(days=2),
            ),
            ClvRecord(
                signal_id=ncaab_signal.id,
                event_id=ncaab_event,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.0,
                entry_price=None,
                close_line=-3.2,
                close_price=None,
                clv_line=-0.2,
                clv_prob=None,
                computed_at=now - timedelta(days=2),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-summary-sport@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/clv/summary?days=30&sport_key=basketball_nba&signal_type=MOVE&market=spreads&min_samples=1",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["count"] == 1


async def test_clv_recap_buckets_by_game_commence_time_not_computed_at(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_recap_commence_bucket"
    commence_time = now - timedelta(days=3, hours=2)
    signal = _signal(
        event_id=event_id,
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=commence_time - timedelta(hours=4),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all([_game(event_id=event_id, commence_time=commence_time), signal])
    await db_session.flush()

    db_session.add(
        ClvRecord(
            signal_id=signal.id,
            event_id=event_id,
            signal_type="MOVE",
            market="spreads",
            outcome_name="BOS",
            entry_line=-3.5,
            entry_price=None,
            close_line=-4.0,
            close_price=None,
            clv_line=-0.5,
            clv_prob=None,
            computed_at=commence_time + timedelta(days=1),
        )
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-recap-commence@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/clv/recap?days=30&grain=day&signal_type=MOVE&market=spreads",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "day"
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    actual_period_start = datetime.fromisoformat(row["period_start"].replace("Z", "+00:00"))
    expected_period_start = commence_time.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    assert actual_period_start == expected_period_start


async def test_clv_recap_weekly_utc_grouping(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    this_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    latest_week_start = this_week_start - timedelta(days=7)
    prior_week_start = this_week_start - timedelta(days=14)

    seed_events = [
        ("event_perf_recap_week_a", latest_week_start + timedelta(days=1, hours=2)),
        ("event_perf_recap_week_b", latest_week_start + timedelta(days=3, hours=1)),
        ("event_perf_recap_week_c", prior_week_start + timedelta(days=2, hours=3)),
    ]
    for idx, (event_id, commence_time) in enumerate(seed_events):
        signal = _signal(
            event_id=event_id,
            market="spreads",
            signal_type="MOVE",
            strength=78,
            created_at=commence_time - timedelta(hours=4),
            metadata={"outcome_name": "BOS"},
        )
        db_session.add_all([_game(event_id=event_id, commence_time=commence_time), signal])
        await db_session.flush()
        db_session.add(
            ClvRecord(
                signal_id=signal.id,
                event_id=event_id,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-2.0,
                entry_price=None,
                close_line=-2.0 + (0.25 if idx < 2 else -0.1),
                close_price=None,
                clv_line=0.25 if idx < 2 else -0.1,
                clv_prob=None,
                computed_at=now - timedelta(days=1),
            )
        )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-recap-weekly@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/clv/recap?days=60&grain=week&signal_type=MOVE&market=spreads&min_samples=1",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    rows = payload["rows"]
    assert len(rows) >= 2

    by_period = {
        datetime.fromisoformat(row["period_start"].replace("Z", "+00:00")): row
        for row in rows
    }
    assert by_period[latest_week_start]["count"] == 2
    assert by_period[prior_week_start]["count"] == 1


async def test_clv_recap_respects_filters_and_min_samples(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    commence_time = now - timedelta(days=4)

    move_events = ["event_perf_recap_filter_1", "event_perf_recap_filter_2"]
    for event_id in move_events:
        signal = _signal(
            event_id=event_id,
            market="spreads",
            signal_type="MOVE",
            strength=82,
            created_at=commence_time - timedelta(hours=2),
            metadata={"outcome_name": "BOS"},
        )
        db_session.add_all([_game(event_id=event_id, commence_time=commence_time), signal])
        await db_session.flush()
        db_session.add(
            ClvRecord(
                signal_id=signal.id,
                event_id=event_id,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.0,
                entry_price=None,
                close_line=-3.2,
                close_price=None,
                clv_line=-0.2,
                clv_prob=None,
                computed_at=now - timedelta(days=3),
            )
        )

    totals_event = "event_perf_recap_filter_totals"
    totals_signal = _signal(
        event_id=totals_event,
        market="totals",
        signal_type="DISLOCATION",
        strength=88,
        created_at=commence_time - timedelta(hours=1),
        metadata={"outcome_name": "Over"},
    )
    db_session.add_all([_game(event_id=totals_event, commence_time=commence_time), totals_signal])
    await db_session.flush()
    db_session.add(
        ClvRecord(
            signal_id=totals_signal.id,
            event_id=totals_event,
            signal_type="DISLOCATION",
            market="totals",
            outcome_name="Over",
            entry_line=220.0,
            entry_price=None,
            close_line=221.0,
            close_price=None,
            clv_line=1.0,
            clv_prob=None,
            computed_at=now - timedelta(days=3),
        )
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-recap-filter@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/clv/recap?days=30&grain=day&min_samples=2&signal_type=MOVE&market=spreads",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["signal_type"] == "MOVE"
    assert row["market"] == "spreads"
    assert row["count"] == 2


async def test_signal_quality_endpoint_filters_by_dispersion(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_signal_quality"
    db_session.add_all(
        [
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                strength=78,
                created_at=now - timedelta(minutes=20),
                metadata={
                    "outcome_name": "BOS",
                    "dispersion": 0.35,
                    "delta": 1.2,
                    "book_key": "draftkings",
                },
            ),
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                strength=82,
                created_at=now - timedelta(minutes=10),
                metadata={
                    "outcome_name": "BOS",
                    "dispersion": 1.45,
                    "delta": 1.8,
                    "book_key": "fanduel",
                },
            ),
            _signal(
                event_id=event_id,
                market="totals",
                signal_type="MOVE",
                strength=45,
                created_at=now - timedelta(minutes=15),
                metadata={"outcome_name": "Over"},
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-quality@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/quality"
        "?days=7&signal_type=DISLOCATION&market=spreads&min_strength=60&max_dispersion=0.5",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["signal_type"] == "DISLOCATION"
    assert payload[0]["book_key"] == "draftkings"


async def test_signal_quality_endpoint_filters_by_sport_key(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    nba_event = "event_perf_signal_quality_sport_nba"
    nfl_event = "event_perf_signal_quality_sport_nfl"
    db_session.add_all(
        [
            _game(event_id=nba_event, commence_time=now + timedelta(hours=2), sport_key="basketball_nba"),
            _game(event_id=nfl_event, commence_time=now + timedelta(hours=3), sport_key="americanfootball_nfl"),
            _signal(
                event_id=nba_event,
                market="spreads",
                signal_type="MOVE",
                strength=80,
                created_at=now - timedelta(minutes=15),
                metadata={"outcome_name": "BOS"},
            ),
            _signal(
                event_id=nfl_event,
                market="spreads",
                signal_type="MOVE",
                strength=82,
                created_at=now - timedelta(minutes=10),
                metadata={"outcome_name": "BOS"},
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-quality-sport@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/quality?days=7&sport_key=americanfootball_nfl&signal_type=MOVE&market=spreads",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["event_id"] == nfl_event


async def test_signal_quality_endpoint_includes_alert_decisions_with_user_rules(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_signal_decision"
    email = "perf-quality-rules@example.com"
    token = await _register_pro_user(async_client, db_session, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    db_session.add(
        DiscordConnection(
            user_id=user.id,
            webhook_url="https://discord.example/webhook",
            is_enabled=True,
            alert_spreads=True,
            alert_totals=True,
            alert_multibook=True,
            min_strength=60,
            thresholds_json={"min_books_affected": 4, "max_dispersion": 0.5, "cooldown_minutes": 10},
        )
    )
    db_session.add_all(
        [
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                strength=78,
                created_at=now - timedelta(minutes=20),
                metadata={"outcome_name": "BOS", "dispersion": 0.4},
            ),
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                strength=80,
                created_at=now - timedelta(minutes=10),
                metadata={"outcome_name": "BOS", "dispersion": 0.8},
            ),
        ]
    )
    await db_session.flush()
    signals = (await db_session.execute(select(Signal).where(Signal.event_id == event_id))).scalars().all()
    signals[0].books_affected = 5
    signals[1].books_affected = 2
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/quality?days=7&signal_type=DISLOCATION&market=spreads&apply_alert_rules=true&include_hidden=true",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    decisions = {row["alert_decision"] for row in payload}
    assert "sent" in decisions
    assert "hidden" in decisions
    hidden_row = next(row for row in payload if row["alert_decision"] == "hidden")
    assert "below min" in hidden_row["alert_reason"] or "above max" in hidden_row["alert_reason"]


async def test_signal_quality_endpoint_supports_enrichment_filters(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_signal_quality_enriched"
    other_event_id = "event_perf_signal_quality_enriched_other"
    db_session.add_all(
        [
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="MOVE",
                strength=85,
                created_at=now - timedelta(minutes=30),
                metadata={"outcome_name": "BOS"},
                velocity=0.025,
                acceleration=0.004,
                time_bucket="PRETIP",
                composite_score=83,
                minutes_to_tip=42,
                computed_at=now - timedelta(minutes=29),
            ),
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="MOVE",
                strength=80,
                created_at=now - timedelta(minutes=24),
                metadata={"outcome_name": "BOS"},
                velocity=0.021,
                acceleration=0.002,
                time_bucket="LATE",
                composite_score=59,
                minutes_to_tip=220,
                computed_at=now - timedelta(minutes=23),
            ),
            _signal(
                event_id=other_event_id,
                market="spreads",
                signal_type="MOVE",
                strength=90,
                created_at=now - timedelta(minutes=18),
                metadata={"outcome_name": "BOS"},
                velocity=0.009,
                acceleration=0.001,
                time_bucket="PRETIP",
                composite_score=92,
                minutes_to_tip=35,
                computed_at=now - timedelta(minutes=17),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-quality-enriched@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/quality",
        params={
            "days": 7,
            "signal_type": "MOVE",
            "market": "spreads",
            "min_score": 70,
            "time_bucket": "PRETIP",
            "velocity_gt": 0.01,
            "game_id": event_id,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["event_id"] == event_id
    assert row["composite_score"] == 83
    assert row["time_bucket"] == "PRETIP"
    assert row["velocity"] == pytest.approx(0.025)
    assert row["acceleration"] == pytest.approx(0.004)
    assert row["minutes_to_tip"] == 42
    assert row["computed_at"] is not None


async def test_signal_quality_endpoint_since_overrides_created_after(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_signal_quality_since"
    db_session.add(
        _signal(
            event_id=event_id,
            market="spreads",
            signal_type="MOVE",
            strength=86,
            created_at=now - timedelta(days=5),
            metadata={"outcome_name": "BOS"},
            composite_score=77,
            time_bucket="MID",
            velocity=0.014,
            minutes_to_tip=700,
            computed_at=now - timedelta(days=5),
        )
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-quality-since@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    without_since = await async_client.get(
        "/api/v1/intel/signals/quality",
        params={
            "days": 1,
            "created_after": (now - timedelta(days=1)).isoformat(),
            "game_id": event_id,
            "signal_type": "MOVE",
            "market": "spreads",
        },
        headers=headers,
    )
    assert without_since.status_code == 200
    assert without_since.json() == []

    with_since = await async_client.get(
        "/api/v1/intel/signals/quality",
        params={
            "days": 1,
            "created_after": (now - timedelta(days=1)).isoformat(),
            "since": (now - timedelta(days=7)).isoformat(),
            "game_id": event_id,
            "signal_type": "MOVE",
            "market": "spreads",
        },
        headers=headers,
    )
    assert with_since.status_code == 200
    payload = with_since.json()
    assert len(payload) == 1
    assert payload[0]["event_id"] == event_id


async def test_signal_quality_endpoint_type_alias_and_nullable_enrichment_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_signal_quality_type_alias"
    db_session.add(
        _signal(
            event_id=event_id,
            market="spreads",
            signal_type="MOVE",
            strength=80,
            created_at=now - timedelta(minutes=15),
            metadata={"outcome_name": "BOS"},
        )
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-quality-type-alias@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/quality",
        params={"days": 7, "type": "MOVE", "market": "spreads", "game_id": event_id},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    row = payload[0]
    for field in (
        "velocity",
        "acceleration",
        "time_bucket",
        "composite_score",
        "minutes_to_tip",
        "computed_at",
    ):
        assert field in row
    assert row["velocity"] is None
    assert row["composite_score"] is None


async def test_signal_quality_weekly_summary_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    email = "perf-weekly-summary@example.com"
    token = await _register_pro_user(async_client, db_session, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    db_session.add(
        DiscordConnection(
            user_id=user.id,
            webhook_url="https://discord.example/webhook",
            is_enabled=True,
            alert_spreads=True,
            alert_totals=True,
            alert_multibook=True,
            min_strength=60,
            thresholds_json={"min_books_affected": 3, "cooldown_minutes": 10},
        )
    )

    eligible_signal = _signal(
        event_id="event_perf_weekly_1",
        market="spreads",
        signal_type="MOVE",
        strength=82,
        created_at=now - timedelta(days=2),
        metadata={"outcome_name": "BOS"},
    )
    hidden_signal = _signal(
        event_id="event_perf_weekly_2",
        market="spreads",
        signal_type="MOVE",
        strength=75,
        created_at=now - timedelta(days=1),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all([eligible_signal, hidden_signal])
    await db_session.flush()
    eligible_signal.books_affected = 4
    hidden_signal.books_affected = 1
    db_session.add(
        ClvRecord(
            signal_id=eligible_signal.id,
            event_id=eligible_signal.event_id,
            signal_type=eligible_signal.signal_type,
            market=eligible_signal.market,
            outcome_name="BOS",
            entry_line=-3.5,
            entry_price=None,
            close_line=-4.0,
            close_price=None,
            clv_line=-0.5,
            clv_prob=None,
            computed_at=now - timedelta(hours=6),
        )
    )
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/weekly-summary?days=7&signal_type=MOVE&market=spreads&apply_alert_rules=true",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_signals"] >= 2
    assert payload["eligible_signals"] >= 1
    assert payload["hidden_signals"] >= 1
    assert payload["clv_samples"] >= 1
    assert 0.0 <= payload["sent_rate_pct"] <= 100.0


async def test_signal_lifecycle_summary_endpoint_counts_states(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    email = "perf-lifecycle@example.com"
    token = await _register_pro_user(async_client, db_session, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    db_session.add(
        DiscordConnection(
            user_id=user.id,
            webhook_url="https://discord.example/webhook",
            is_enabled=True,
            alert_spreads=True,
            alert_totals=True,
            alert_multibook=True,
            min_strength=60,
            thresholds_json={"min_books_affected": 4, "cooldown_minutes": 10},
        )
    )

    sent_signal = _signal(
        event_id="event_perf_lifecycle_sent",
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=1),
        metadata={"outcome_name": "BOS"},
    )
    filtered_signal = _signal(
        event_id="event_perf_lifecycle_filtered",
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=1),
        metadata={"outcome_name": "BOS"},
    )
    stale_signal = _signal(
        event_id="event_perf_lifecycle_stale",
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=12),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all([sent_signal, filtered_signal, stale_signal])
    await db_session.flush()
    sent_signal.books_affected = 5
    filtered_signal.books_affected = 1
    stale_signal.books_affected = 5
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/signals/lifecycle?days=7&signal_type=MOVE&market=spreads&apply_alert_rules=true",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_detected"] >= 3
    assert payload["sent_signals"] >= 1
    assert payload["filtered_signals"] >= 1
    assert payload["stale_signals"] >= 1
    assert payload["not_sent_signals"] >= 2
    assert isinstance(payload["top_filtered_reasons"], list)


async def test_actionable_book_card_uses_latest_per_book(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_actionable"

    signal = _signal(
        event_id=event_id,
        market="spreads",
        signal_type="MOVE",
        strength=74,
        created_at=now - timedelta(minutes=30),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add(signal)
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-3.0,
                price=-112,
                fetched_at=now - timedelta(minutes=9),
            ),
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.0,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=8),
            ),
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.5,
                price=-108,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=6,
                fetched_at=now - timedelta(minutes=3),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-actionable@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        f"/api/v1/intel/books/actionable?event_id={event_id}&signal_id={signal.id}",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["books_considered"] == 2
    assert payload["consensus_source"] == "persisted_consensus"
    assert payload["best_book_key"] == "draftkings"
    assert payload["execution_rank"] >= 1
    assert payload["freshness_bucket"] in {"fresh", "aging", "stale"}
    assert isinstance(payload["actionable_reason"], str) and payload["actionable_reason"]
    assert len(payload["top_books"]) <= 2
    quote_map = {quote["sportsbook_key"]: quote for quote in payload["quotes"]}
    assert quote_map["draftkings"]["line"] == -2.0
    assert quote_map["fanduel"]["line"] == -3.5


async def test_actionable_book_card_batch_endpoint_returns_multiple_cards(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_actionable_batch"

    signal_one = _signal(
        event_id=event_id,
        market="spreads",
        signal_type="MOVE",
        strength=72,
        created_at=now - timedelta(minutes=40),
        metadata={"outcome_name": "BOS"},
    )
    signal_two = _signal(
        event_id=event_id,
        market="totals",
        signal_type="DISLOCATION",
        strength=80,
        created_at=now - timedelta(minutes=35),
        metadata={"outcome_name": "Over"},
    )
    db_session.add_all([signal_one, signal_two])
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.5,
                price=-110,
                fetched_at=now - timedelta(minutes=4),
            ),
            _snapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-108,
                fetched_at=now - timedelta(minutes=3),
            ),
            _snapshot(
                event_id=event_id,
                market="totals",
                outcome_name="Over",
                sportsbook_key="draftkings",
                line=221.0,
                price=-110,
                fetched_at=now - timedelta(minutes=4),
            ),
            _snapshot(
                event_id=event_id,
                market="totals",
                outcome_name="Over",
                sportsbook_key="fanduel",
                line=222.0,
                price=-108,
                fetched_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-actionable-batch@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        f"/api/v1/intel/books/actionable/batch?event_id={event_id}&signal_ids={signal_one.id},{signal_two.id}",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    returned_ids = {row["signal_id"] for row in payload}
    assert str(signal_one.id) in returned_ids
    assert str(signal_two.id) in returned_ids


async def test_opportunities_endpoint_returns_ranked_opportunities(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_a = "event_perf_opportunity_a"
    event_b = "event_perf_opportunity_b"
    commence = now + timedelta(hours=2)

    signal_a = _signal(
        event_id=event_a,
        market="spreads",
        signal_type="MOVE",
        strength=85,
        created_at=now - timedelta(minutes=12),
        metadata={"outcome_name": "BOS"},
    )
    signal_b = _signal(
        event_id=event_b,
        market="spreads",
        signal_type="MOVE",
        strength=70,
        created_at=now - timedelta(minutes=6),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all(
        [
            _game(event_id=event_a, commence_time=commence),
            _game(event_id=event_b, commence_time=commence + timedelta(minutes=30)),
            signal_a,
            signal_b,
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=event_a,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.0,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_a,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_b,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-3.4,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_b,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.5,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_a,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_b,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.5,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-opportunities@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&signal_type=MOVE&market=spreads&min_strength=60&limit=10",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 2
    assert payload[0]["signal_id"] == str(signal_a.id)
    assert payload[0]["event_id"] == event_a
    assert payload[0]["game_label"] == "NYK @ BOS"
    assert payload[0]["opportunity_score"] >= payload[1]["opportunity_score"]
    assert payload[0]["score_basis"] == "opportunity"
    assert payload[0]["ranking_score"] == payload[0]["opportunity_score"]
    assert "context_score" in payload[0]
    assert "blended_score" in payload[0]
    assert isinstance(payload[0]["score_summary"], str) and payload[0]["score_summary"]
    assert "strength" in payload[0]["score_components"]
    assert "delta" in payload[0]["score_components"]


async def test_opportunities_dedupe_and_stale_filter_toggle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    dedupe_event = "event_perf_opportunity_dedupe"
    stale_event = "event_perf_opportunity_stale"
    commence = now + timedelta(hours=3)

    stronger = _signal(
        event_id=dedupe_event,
        market="spreads",
        signal_type="MOVE",
        strength=88,
        created_at=now + timedelta(minutes=5),
        metadata={"outcome_name": "BOS"},
    )
    weaker = _signal(
        event_id=dedupe_event,
        market="spreads",
        signal_type="MOVE",
        strength=62,
        created_at=now + timedelta(minutes=4),
        metadata={"outcome_name": "BOS"},
    )
    stale_signal = _signal(
        event_id=stale_event,
        market="totals",
        signal_type="STEAM",
        strength=100,
        created_at=now + timedelta(minutes=3),
        metadata={"outcome_name": "Over"},
    )
    db_session.add_all(
        [
            _game(event_id=dedupe_event, commence_time=commence),
            _game(event_id=stale_event, commence_time=commence + timedelta(minutes=45)),
            stronger,
            weaker,
            stale_signal,
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=dedupe_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.0,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=dedupe_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=stale_event,
                market="totals",
                outcome_name="Over",
                sportsbook_key="draftkings",
                line=232.0,
                price=-115,
                fetched_at=now - timedelta(days=2),
            ),
            _snapshot(
                event_id=stale_event,
                market="totals",
                outcome_name="Over",
                sportsbook_key="fanduel",
                line=234.0,
                price=-110,
                fetched_at=now - timedelta(days=2, minutes=2),
            ),
            MarketConsensusSnapshot(
                event_id=dedupe_event,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=stale_event,
                market="totals",
                outcome_name="Over",
                consensus_line=235.0,
                consensus_price=-110.0,
                dispersion=0.6,
                books_count=5,
                fetched_at=now - timedelta(days=2, minutes=2),
            ),
        ]
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-opportunities-toggle@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    default_response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&market=spreads&min_strength=80&limit=20",
        headers=headers,
    )
    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert all(row["freshness_bucket"] != "stale" for row in default_payload)
    dedupe_rows = [row for row in default_payload if row["event_id"] == dedupe_event and row["market"] == "spreads"]
    assert len(dedupe_rows) == 1
    assert dedupe_rows[0]["signal_id"] == str(stronger.id)

    include_stale_response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&signal_type=STEAM&market=totals&min_strength=100&include_stale=true&limit=50",
        headers=headers,
    )
    assert include_stale_response.status_code == 200
    include_stale_payload = include_stale_response.json()
    stale_rows = [row for row in include_stale_payload if row["event_id"] == stale_event]
    assert len(stale_rows) == 1, include_stale_payload
    assert stale_rows[0]["opportunity_status"] == "stale"
    assert stale_rows[0]["opportunity_score"] <= 69


async def test_opportunities_can_rank_by_blended_score_when_enabled(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    event_low_context = "event_perf_opportunity_blend_low_context"
    event_high_context = "event_perf_opportunity_blend_high_context"
    commence = now + timedelta(hours=2)

    # Keep core opportunity score similar so context blend decides ordering.
    signal_low = _signal(
        event_id=event_low_context,
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=8),
        metadata={"outcome_name": "BOS"},
    )
    signal_high = _signal(
        event_id=event_high_context,
        market="spreads",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=7),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all(
        [
            _game(event_id=event_low_context, commence_time=commence),
            _game(event_id=event_high_context, commence_time=commence + timedelta(minutes=20)),
            signal_low,
            signal_high,
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=event_low_context,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.5,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_low_context,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            _snapshot(
                event_id=event_high_context,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.5,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_high_context,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_low_context,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.5,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_high_context,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.5,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    async def _fake_context(_db: AsyncSession, event_id: str) -> dict:
        score = 20 if event_id == event_low_context else 95
        return {
            "event_id": event_id,
            "components": [
                {"component": "injuries", "status": "computed", "score": score},
                {"component": "player_props", "status": "computed", "score": score},
                {"component": "pace", "status": "computed", "score": score},
            ],
        }

    monkeypatch.setattr(performance_intel, "build_context_score", _fake_context)
    monkeypatch.setattr(performance_intel.settings, "context_score_blend_enabled", True)
    monkeypatch.setattr(performance_intel.settings, "context_score_blend_weight_opportunity", 0.8)
    monkeypatch.setattr(performance_intel.settings, "context_score_blend_weight_context", 0.2)

    token = await _register_pro_user(async_client, db_session, "perf-opportunities-blend@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&signal_type=MOVE&market=spreads&min_strength=60&limit=10",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 2
    assert payload[0]["score_basis"] == "blended"
    assert payload[0]["event_id"] == event_high_context
    assert payload[0]["blended_score"] >= payload[1]["blended_score"]


async def test_opportunities_teaser_endpoint_returns_delayed_free_rows(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    delayed_event = "event_perf_opportunity_teaser_delayed"
    fresh_event = "event_perf_opportunity_teaser_fresh"
    commence = now + timedelta(hours=2)

    delayed_signal = _signal(
        event_id=delayed_event,
        market="spreads",
        signal_type="MOVE",
        strength=88,
        created_at=now - timedelta(minutes=25),
        metadata={"outcome_name": "BOS"},
    )
    fresh_signal = _signal(
        event_id=fresh_event,
        market="spreads",
        signal_type="MOVE",
        strength=82,
        created_at=now - timedelta(minutes=2),
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all(
        [
            _game(event_id=delayed_event, commence_time=commence),
            _game(event_id=fresh_event, commence_time=commence + timedelta(minutes=30)),
            delayed_signal,
            fresh_signal,
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=delayed_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.0,
                price=-110,
                fetched_at=now - timedelta(minutes=3),
            ),
            _snapshot(
                event_id=delayed_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=fresh_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="draftkings",
                line=-2.5,
                price=-110,
                fetched_at=now - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=fresh_event,
                market="spreads",
                outcome_name="BOS",
                sportsbook_key="fanduel",
                line=-3.0,
                price=-110,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=delayed_event,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=fresh_event,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=6,
                fetched_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    free_token = await _register(async_client, "perf-opportunity-teaser-free@example.com")
    free_headers = {"Authorization": f"Bearer {free_token}"}
    response = await async_client.get("/api/v1/intel/opportunities/teaser?days=7&limit=5", headers=free_headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    event_ids = {row["event_id"] for row in payload}
    assert delayed_event in event_ids
    assert fresh_event not in event_ids
    assert "best_book_key" not in payload[0]


async def test_public_teaser_opportunities_anonymous_ok(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_ok",
        sport_key="basketball_nba",
        home_team="Oklahoma City Thunder",
        away_team="Cleveland Cavaliers",
        commence_time=now + timedelta(hours=4),
        created_at=now - timedelta(minutes=35),
        strength=92,
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/opportunities?sport_key=basketball_nba&limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    first = payload[0]
    assert set(first.keys()) == {
        "game_label",
        "commence_time",
        "signal_type",
        "market",
        "outcome_name",
        "score_status",
        "freshness_label",
        "delta_display",
    }
    assert first["score_status"] in {"ACTIONABLE", "MONITOR", "STALE"}
    assert first["freshness_label"] in {"Fresh", "Aging", "Stale"}
    assert "event_id" not in first


async def test_public_teaser_respects_sport_filter(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_nba",
        sport_key="basketball_nba",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=now + timedelta(hours=5),
        created_at=now - timedelta(minutes=40),
        strength=90,
    )
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_ncaab",
        sport_key="basketball_ncaab",
        home_team="Duke Blue Devils",
        away_team="North Carolina Tar Heels",
        commence_time=now + timedelta(hours=5),
        created_at=now - timedelta(minutes=40),
        strength=90,
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/opportunities?sport_key=basketball_ncaab&limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert all("North Carolina Tar Heels @ Duke Blue Devils" == row["game_label"] for row in payload)


async def test_public_teaser_limit_capped(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    for idx in range(12):
        await _seed_public_teaser_signal(
            db_session,
            event_id=f"event_public_teaser_limit_{idx}",
            sport_key="basketball_nba",
            home_team=f"Home {idx}",
            away_team=f"Away {idx}",
            commence_time=now + timedelta(hours=idx + 1),
            created_at=now - timedelta(minutes=45 + idx),
            strength=88,
        )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/opportunities?sport_key=basketball_nba&limit=50")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) <= 8


async def test_public_teaser_excludes_stale_rows(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_fresh_only",
        sport_key="basketball_nba",
        home_team="Phoenix Suns",
        away_team="Denver Nuggets",
        commence_time=now + timedelta(hours=2),
        created_at=now - timedelta(minutes=35),
        quote_fetched_at=now - timedelta(minutes=1),
    )
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_stale_only",
        sport_key="basketball_nba",
        home_team="Golden State Warriors",
        away_team="Los Angeles Clippers",
        commence_time=now + timedelta(hours=2),
        created_at=now - timedelta(minutes=35),
        quote_fetched_at=now - timedelta(minutes=40),
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/opportunities?sport_key=basketball_nba&limit=8")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    labels = [row["game_label"] for row in payload]
    assert "Denver Nuggets @ Phoenix Suns" in labels
    assert "Los Angeles Clippers @ Golden State Warriors" not in labels
    assert all(row["freshness_label"] != "Stale" for row in payload)


async def test_public_teaser_redaction_no_internal_ids(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_redaction",
        sport_key="basketball_nba",
        home_team="Memphis Grizzlies",
        away_team="Sacramento Kings",
        commence_time=now + timedelta(hours=3),
        created_at=now - timedelta(minutes=50),
        strength=86,
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/opportunities?sport_key=basketball_nba")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    for row in payload:
        assert "event_id" not in row
        assert "signal_id" not in row
        assert "best_book_key" not in row


async def test_public_teaser_kpis_anonymous_ok(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_kpi_a",
        sport_key="basketball_nba",
        home_team="Milwaukee Bucks",
        away_team="Chicago Bulls",
        commence_time=now + timedelta(hours=2),
        created_at=now - timedelta(minutes=32),
        strength=91,
    )
    await _seed_public_teaser_signal(
        db_session,
        event_id="event_public_teaser_kpi_b",
        sport_key="basketball_nba",
        home_team="Miami Heat",
        away_team="Orlando Magic",
        commence_time=now + timedelta(hours=2),
        created_at=now - timedelta(minutes=28),
        strength=84,
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/public/teaser/kpis?sport_key=basketball_nba&window_hours=24")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "signals_in_window",
        "books_tracked_estimate",
        "pct_actionable",
        "pct_fresh",
        "updated_at",
    }
    assert payload["signals_in_window"] >= 2
    assert payload["books_tracked_estimate"] >= 2
    assert 0 <= payload["pct_actionable"] <= 100
    assert 0 <= payload["pct_fresh"] <= 100


async def test_teaser_interaction_event_endpoint_accepts_valid_payload(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _ensure_teaser_events_table(db_session)
    free_token = await _register(async_client, "perf-teaser-event-free@example.com")
    headers = {"Authorization": f"Bearer {free_token}"}
    response = await async_client.post(
        "/api/v1/intel/teaser/events",
        headers=headers,
        json={"event_name": "viewed_teaser", "source": "performance_page", "sport_key": "basketball_nba"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    invalid = await async_client.post(
        "/api/v1/intel/teaser/events",
        headers=headers,
        json={"event_name": "invalid_event"},
    )
    assert invalid.status_code == 422


async def test_new_intel_endpoints_gate_free_vs_pro(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    free_token = await _register(async_client, "perf-free@example.com")
    pro_token = await _register_pro_user(async_client, db_session, "perf-pro@example.com")

    free_headers = {"Authorization": f"Bearer {free_token}"}
    pro_headers = {"Authorization": f"Bearer {pro_token}"}

    free_quality = await async_client.get("/api/v1/intel/signals/quality?days=7", headers=free_headers)
    assert free_quality.status_code == 403

    pro_quality = await async_client.get("/api/v1/intel/signals/quality?days=7", headers=pro_headers)
    assert pro_quality.status_code == 200

    free_weekly = await async_client.get("/api/v1/intel/signals/weekly-summary?days=7", headers=free_headers)
    assert free_weekly.status_code == 403

    pro_weekly = await async_client.get("/api/v1/intel/signals/weekly-summary?days=7", headers=pro_headers)
    assert pro_weekly.status_code == 200

    free_lifecycle = await async_client.get("/api/v1/intel/signals/lifecycle?days=7", headers=free_headers)
    assert free_lifecycle.status_code == 403

    pro_lifecycle = await async_client.get("/api/v1/intel/signals/lifecycle?days=7", headers=pro_headers)
    assert pro_lifecycle.status_code == 200

    teaser = await async_client.get("/api/v1/intel/clv/teaser?days=30", headers=free_headers)
    assert teaser.status_code == 200
    teaser_payload = teaser.json()
    assert teaser_payload["days"] == 30

    free_opportunity_teaser = await async_client.get("/api/v1/intel/opportunities/teaser?days=7", headers=free_headers)
    assert free_opportunity_teaser.status_code == 200

    free_scorecards = await async_client.get("/api/v1/intel/clv/scorecards?days=30", headers=free_headers)
    assert free_scorecards.status_code == 403

    pro_scorecards = await async_client.get("/api/v1/intel/clv/scorecards?days=30", headers=pro_headers)
    assert pro_scorecards.status_code == 200

    free_recap = await async_client.get("/api/v1/intel/clv/recap?days=30&grain=day", headers=free_headers)
    assert free_recap.status_code == 403

    pro_recap = await async_client.get("/api/v1/intel/clv/recap?days=30&grain=day", headers=pro_headers)
    assert pro_recap.status_code == 200

    free_actionable_batch = await async_client.get(
        "/api/v1/intel/books/actionable/batch?event_id=event_any&signal_ids=00000000-0000-0000-0000-000000000001",
        headers=free_headers,
    )
    assert free_actionable_batch.status_code == 403

    free_opportunities = await async_client.get("/api/v1/intel/opportunities?days=7", headers=free_headers)
    assert free_opportunities.status_code == 403

    pro_opportunities = await async_client.get("/api/v1/intel/opportunities?days=7", headers=pro_headers)
    assert pro_opportunities.status_code == 200


async def test_clv_scorecards_rank_and_tier_by_quality(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_perf_scorecards"

    # Stronger profile: higher samples and higher positive rate.
    for idx in range(30):
        signal = _signal(
            event_id=event_id,
            market="spreads",
            signal_type="MOVE",
            strength=82,
            created_at=now - timedelta(days=5, minutes=idx),
            metadata={"outcome_name": "BOS"},
        )
        db_session.add(signal)
        await db_session.flush()

        is_positive = idx < 22
        db_session.add(
            ClvRecord(
                signal_id=signal.id,
                event_id=event_id,
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.0,
                entry_price=None,
                close_line=-3.0 + (0.4 if is_positive else -0.15),
                close_price=None,
                clv_line=0.4 if is_positive else -0.15,
                clv_prob=None,
                computed_at=now - timedelta(days=4, minutes=idx),
            )
        )

    # Weaker profile: lower samples and flat/noisy edge.
    for idx in range(12):
        signal = _signal(
            event_id=event_id,
            market="totals",
            signal_type="DISLOCATION",
            strength=70,
            created_at=now - timedelta(days=4, minutes=idx),
            metadata={"outcome_name": "Over", "dispersion": 1.1},
        )
        db_session.add(signal)
        await db_session.flush()

        is_positive = idx % 2 == 0
        db_session.add(
            ClvRecord(
                signal_id=signal.id,
                event_id=event_id,
                signal_type="DISLOCATION",
                market="totals",
                outcome_name="Over",
                entry_line=220.0,
                entry_price=None,
                close_line=220.0 + (0.08 if is_positive else -0.08),
                close_price=None,
                clv_line=0.08 if is_positive else -0.08,
                clv_prob=None,
                computed_at=now - timedelta(days=3, minutes=idx),
            )
        )

    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "perf-scorecards@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.get(
        "/api/v1/intel/clv/scorecards?days=30&min_samples=10",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()

    move_scorecard = next(
        row for row in payload if row["signal_type"] == "MOVE" and row["market"] == "spreads"
    )
    dislocation_scorecard = next(
        row for row in payload if row["signal_type"] == "DISLOCATION" and row["market"] == "totals"
    )

    assert move_scorecard["count"] == 30
    assert dislocation_scorecard["count"] == 12
    assert move_scorecard["confidence_score"] > dislocation_scorecard["confidence_score"]
    assert move_scorecard["confidence_tier"] in {"A", "B"}
    assert dislocation_scorecard["confidence_tier"] == "C"
