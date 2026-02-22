from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.closing_consensus import ClosingConsensus
from app.models.clv_record import ClvRecord
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.signal import Signal
from app.models.user import User
from app.services.closing import cleanup_old_closing_consensus, compute_and_persist_closing_consensus
from app.services.clv import american_to_implied_prob, cleanup_old_clv_records, compute_and_persist_clv


def _game(event_id: str, commence_time: datetime) -> Game:
    return Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="NYK",
        away_team="BOS",
    )


def _consensus(
    *,
    event_id: str,
    market: str,
    outcome_name: str,
    line: float | None,
    price: float | None,
    fetched_at: datetime,
    books_count: int = 6,
) -> MarketConsensusSnapshot:
    return MarketConsensusSnapshot(
        event_id=event_id,
        market=market,
        outcome_name=outcome_name,
        consensus_line=line,
        consensus_price=price,
        dispersion=0.3,
        books_count=books_count,
        fetched_at=fetched_at,
    )


def _signal(
    *,
    event_id: str,
    market: str,
    signal_type: str,
    created_at: datetime,
    metadata: dict,
    from_value: float = -3.0,
    to_value: float = -3.5,
    from_price: int | None = -110,
    to_price: int | None = -110,
) -> Signal:
    direction = "UP" if to_value > from_value else "DOWN"
    return Signal(
        event_id=event_id,
        market=market,
        signal_type=signal_type,
        direction=direction,
        from_value=from_value,
        to_value=to_value,
        from_price=from_price,
        to_price=to_price,
        window_minutes=10,
        books_affected=2,
        velocity_minutes=2.0,
        strength_score=70,
        created_at=created_at,
        metadata_json=metadata,
    )


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ClvPass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_closing_consensus_uses_last_snapshot_before_commence(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_clv_close_selection"
    commence = now - timedelta(hours=1)
    latest_pre_close_at = commence - timedelta(minutes=2)

    db_session.add(_game(event_id, commence))
    db_session.add_all(
        [
            _consensus(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                line=-3.0,
                price=-110.0,
                fetched_at=commence - timedelta(minutes=20),
            ),
            _consensus(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                line=-3.5,
                price=-108.0,
                fetched_at=latest_pre_close_at,
            ),
            _consensus(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                line=-4.0,
                price=-106.0,
                fetched_at=commence + timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    upserts = await compute_and_persist_closing_consensus(db_session, [event_id])
    assert upserts == 1

    closing = (
        await db_session.execute(
            select(ClosingConsensus).where(
                ClosingConsensus.event_id == event_id,
                ClosingConsensus.market == "spreads",
                ClosingConsensus.outcome_name == "BOS",
            )
        )
    ).scalar_one()
    assert closing.close_line == -3.5
    assert closing.close_fetched_at == latest_pre_close_at


async def test_compute_clv_creates_one_record_per_signal_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_clv_idempotent"
    commence = now - timedelta(hours=2)

    db_session.add(_game(event_id, commence))
    db_session.add(
        _consensus(
            event_id=event_id,
            market="spreads",
            outcome_name="BOS",
            line=-4.0,
            price=-110.0,
            fetched_at=commence - timedelta(minutes=1),
        )
    )
    db_session.add_all(
        [
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                created_at=commence - timedelta(minutes=20),
                metadata={
                    "outcome_name": "BOS",
                    "book_line": -3.5,
                    "book_price": -108.0,
                },
            ),
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="STEAM",
                created_at=commence - timedelta(minutes=10),
                metadata={
                    "outcome_name": "BOS",
                    "end_line": -3.8,
                },
                from_value=-3.4,
                to_value=-3.8,
                from_price=None,
                to_price=None,
            ),
        ]
    )
    await db_session.commit()

    first = await compute_and_persist_clv(db_session, days_lookback=7)
    second = await compute_and_persist_clv(db_session, days_lookback=7)

    assert first == 2
    assert second == 0

    rows = (
        await db_session.execute(select(ClvRecord).where(ClvRecord.event_id == event_id))
    ).scalars().all()
    assert len(rows) == 2
    assert len({row.signal_id for row in rows}) == 2


async def test_clv_line_and_clv_prob_computation(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_clv_math"
    commence = now - timedelta(hours=3)

    db_session.add(_game(event_id, commence))
    db_session.add_all(
        [
            _consensus(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                line=-4.5,
                price=-110.0,
                fetched_at=commence - timedelta(minutes=1),
            ),
            _consensus(
                event_id=event_id,
                market="h2h",
                outcome_name="BOS",
                line=None,
                price=-125.0,
                fetched_at=commence - timedelta(minutes=1),
            ),
        ]
    )

    db_session.add_all(
        [
            _signal(
                event_id=event_id,
                market="spreads",
                signal_type="DISLOCATION",
                created_at=commence - timedelta(minutes=30),
                metadata={
                    "outcome_name": "BOS",
                    "book_line": -3.5,
                    "book_price": -110.0,
                },
            ),
            _signal(
                event_id=event_id,
                market="h2h",
                signal_type="DISLOCATION",
                created_at=commence - timedelta(minutes=15),
                metadata={
                    "outcome_name": "BOS",
                    "book_line": None,
                    "book_price": 120.0,
                },
                from_value=0.0,
                to_value=0.0,
                from_price=120,
                to_price=120,
            ),
        ]
    )
    await db_session.commit()

    inserted = await compute_and_persist_clv(db_session, days_lookback=7)
    assert inserted == 2

    spread_record = (
        await db_session.execute(
            select(ClvRecord).where(
                ClvRecord.event_id == event_id,
                ClvRecord.market == "spreads",
            )
        )
    ).scalar_one()
    assert spread_record.clv_line == -1.0
    assert spread_record.clv_prob == 0.0

    h2h_record = (
        await db_session.execute(
            select(ClvRecord).where(
                ClvRecord.event_id == event_id,
                ClvRecord.market == "h2h",
            )
        )
    ).scalar_one()
    expected_prob = american_to_implied_prob(-125.0) - american_to_implied_prob(120.0)  # type: ignore[operator]
    assert h2h_record.clv_line is None
    assert h2h_record.clv_prob is not None
    assert abs(h2h_record.clv_prob - expected_prob) < 1e-9


async def test_clv_skips_games_inside_commence_buffer(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    event_id = "event_clv_buffer_skip"
    commence = now - timedelta(minutes=5)

    db_session.add(_game(event_id, commence))
    db_session.add(
        _consensus(
            event_id=event_id,
            market="spreads",
            outcome_name="BOS",
            line=-4.5,
            price=-110.0,
            fetched_at=commence - timedelta(minutes=1),
        )
    )
    db_session.add(
        _signal(
            event_id=event_id,
            market="spreads",
            signal_type="DISLOCATION",
            created_at=commence - timedelta(minutes=2),
            metadata={
                "outcome_name": "BOS",
                "book_line": -4.0,
                "book_price": -108.0,
            },
        )
    )
    await db_session.commit()

    inserted = await compute_and_persist_clv(db_session, days_lookback=7)
    assert inserted == 0

    closing_rows = (
        await db_session.execute(select(ClosingConsensus).where(ClosingConsensus.event_id == event_id))
    ).scalars().all()
    clv_rows = (await db_session.execute(select(ClvRecord).where(ClvRecord.event_id == event_id))).scalars().all()
    assert closing_rows == []
    assert clv_rows == []


async def test_cleanup_old_clv_and_closing_rows(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    old_ts = now - timedelta(days=90)
    new_ts = now - timedelta(days=5)

    old_signal = _signal(
        event_id="event_clv_cleanup_old",
        market="spreads",
        signal_type="MOVE",
        created_at=old_ts,
        metadata={"outcome_name": "BOS"},
    )
    new_signal = _signal(
        event_id="event_clv_cleanup_new",
        market="spreads",
        signal_type="MOVE",
        created_at=new_ts,
        metadata={"outcome_name": "BOS"},
    )
    db_session.add_all([old_signal, new_signal])
    await db_session.flush()

    db_session.add_all(
        [
            ClosingConsensus(
                event_id="event_clv_cleanup_old",
                market="spreads",
                outcome_name="BOS",
                close_line=-4.0,
                close_price=-110.0,
                close_fetched_at=old_ts,
                computed_at=old_ts,
            ),
            ClosingConsensus(
                event_id="event_clv_cleanup_new",
                market="spreads",
                outcome_name="BOS",
                close_line=-3.5,
                close_price=-108.0,
                close_fetched_at=new_ts,
                computed_at=new_ts,
            ),
            ClvRecord(
                signal_id=old_signal.id,
                event_id="event_clv_cleanup_old",
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.5,
                entry_price=None,
                close_line=-4.0,
                close_price=None,
                clv_line=-0.5,
                clv_prob=None,
                computed_at=old_ts,
            ),
            ClvRecord(
                signal_id=new_signal.id,
                event_id="event_clv_cleanup_new",
                signal_type="MOVE",
                market="spreads",
                outcome_name="BOS",
                entry_line=-3.2,
                entry_price=None,
                close_line=-3.5,
                close_price=None,
                clv_line=-0.3,
                clv_prob=None,
                computed_at=new_ts,
            ),
        ]
    )
    await db_session.commit()

    deleted_closing = await cleanup_old_closing_consensus(db_session, retention_days=60)
    deleted_clv = await cleanup_old_clv_records(db_session, retention_days=60)
    assert deleted_closing == 1
    assert deleted_clv == 1

    remaining_closing = (await db_session.execute(select(ClosingConsensus))).scalars().all()
    remaining_clv = (await db_session.execute(select(ClvRecord))).scalars().all()
    assert len(remaining_closing) == 1
    assert remaining_closing[0].event_id == "event_clv_cleanup_new"
    assert len(remaining_clv) == 1
    assert remaining_clv[0].event_id == "event_clv_cleanup_new"


async def test_clv_intel_endpoints_require_pro_and_return_data(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "event_clv_intel_pro"
    commence = now - timedelta(hours=2)

    db_session.add(_game(event_id, commence))
    db_session.add(
        _consensus(
            event_id=event_id,
            market="spreads",
            outcome_name="BOS",
            line=-4.0,
            price=-110.0,
            fetched_at=commence - timedelta(minutes=1),
        )
    )
    db_session.add(
        _signal(
            event_id=event_id,
            market="spreads",
            signal_type="DISLOCATION",
            created_at=commence - timedelta(minutes=30),
            metadata={
                "outcome_name": "BOS",
                "book_line": -3.2,
                "book_price": -108.0,
            },
        )
    )
    await db_session.commit()
    inserted = await compute_and_persist_clv(db_session, days_lookback=7)
    assert inserted == 1

    token = await _register(async_client, "clv-pro@example.com")
    user = (await db_session.execute(select(User).where(User.email == "clv-pro@example.com"))).scalar_one()
    user.tier = "pro"
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}

    event_resp = await async_client.get(f"/api/v1/intel/clv?event_id={event_id}", headers=headers)
    assert event_resp.status_code == 200
    payload = event_resp.json()
    assert len(payload) == 1
    assert payload[0]["event_id"] == event_id
    assert payload[0]["signal_type"] == "DISLOCATION"
    assert payload[0]["strength_score"] == 70

    summary_resp = await async_client.get("/api/v1/intel/clv/summary?days=7", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert any(row["signal_type"] == "DISLOCATION" and row["market"] == "spreads" for row in summary)


async def test_clv_intel_endpoints_block_free_users(async_client: AsyncClient) -> None:
    token = await _register(async_client, "clv-free@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    event_resp = await async_client.get("/api/v1/intel/clv?event_id=event_any", headers=headers)
    assert event_resp.status_code == 403

    summary_resp = await async_client.get("/api/v1/intel/clv/summary?days=7", headers=headers)
    assert summary_resp.status_code == 403
