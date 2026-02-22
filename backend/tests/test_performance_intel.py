from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clv_record import ClvRecord
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.models.user import User


def _signal(
    *,
    event_id: str,
    market: str,
    signal_type: str,
    strength: int,
    created_at: datetime,
    metadata: dict,
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


def _game(*, event_id: str, commence_time: datetime) -> Game:
    return Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="BOS",
        away_team="NYK",
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

    teaser = await async_client.get("/api/v1/intel/clv/teaser?days=30", headers=free_headers)
    assert teaser.status_code == 200
    teaser_payload = teaser.json()
    assert teaser_payload["days"] == 30

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
