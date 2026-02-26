from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.models.user import User
from app.services import performance_intel
from app.services import public_signal_surface
from app.services.discord_alerts import _format_alert
from app.services.signals import serialize_signal


def _signal(
    *,
    event_id: str,
    signal_type: str,
    strength: int,
    created_at: datetime,
) -> Signal:
    return Signal(
        event_id=event_id,
        market="spreads",
        signal_type=signal_type,
        direction="UP",
        from_value=-3.0,
        to_value=-2.5,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=3,
        velocity_minutes=2.0,
        strength_score=strength,
        created_at=created_at,
        metadata_json={"outcome_name": "BOS"},
    )


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    line: float,
    fetched_at: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=fetched_at + timedelta(hours=2),
        home_team="BOS",
        away_team="NYK",
        sportsbook_key=sportsbook_key,
        market="spreads",
        outcome_name="BOS",
        line=line,
        price=-110,
        fetched_at=fetched_at,
    )


async def _register(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StructCorePass123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _register_pro_user(async_client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    token = await _register(async_client, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.tier = "pro"
    await db_session.commit()
    return token


async def _seed_opportunity_event(
    db_session: AsyncSession,
    *,
    event_id: str,
    signal_type: str,
    strength: int,
    created_at: datetime,
) -> None:
    commence_time = created_at + timedelta(hours=2)
    db_session.add(
        Game(
            event_id=event_id,
            sport_key="basketball_nba",
            commence_time=commence_time,
            home_team="BOS",
            away_team="NYK",
        )
    )
    db_session.add(_signal(event_id=event_id, signal_type=signal_type, strength=strength, created_at=created_at))
    await db_session.flush()

    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                sportsbook_key="draftkings",
                line=-2.0,
                fetched_at=created_at - timedelta(minutes=2),
            ),
            _snapshot(
                event_id=event_id,
                sportsbook_key="fanduel",
                line=-3.0,
                fetched_at=created_at - timedelta(minutes=1),
            ),
            MarketConsensusSnapshot(
                event_id=event_id,
                market="spreads",
                outcome_name="BOS",
                consensus_line=-3.5,
                consensus_price=-110.0,
                dispersion=0.4,
                books_count=5,
                fetched_at=created_at - timedelta(minutes=1),
            ),
        ]
    )


async def test_public_structural_core_mode_on_filters_opportunities_feed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setattr(performance_intel.settings, "public_structural_core_mode", True)
    monkeypatch.setattr(public_signal_surface.settings, "public_structural_core_mode", True)

    now = datetime.now(UTC)
    await _seed_opportunity_event(
        db_session,
        event_id="event_struct_core_key_cross_ok",
        signal_type="KEY_CROSS",
        strength=72,
        created_at=now - timedelta(minutes=20),
    )
    await _seed_opportunity_event(
        db_session,
        event_id="event_struct_core_move_hidden",
        signal_type="MOVE",
        strength=90,
        created_at=now - timedelta(minutes=18),
    )
    await _seed_opportunity_event(
        db_session,
        event_id="event_struct_core_key_cross_weak",
        signal_type="KEY_CROSS",
        strength=50,
        created_at=now - timedelta(minutes=16),
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "struct-core-on@example.com")
    response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&market=spreads&include_stale=true&limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert all(row["signal_type"] == "KEY_CROSS" for row in rows)
    assert all(int(row["strength_score"]) >= 55 for row in rows)
    assert all(row.get("display_type") == "STRUCTURAL THRESHOLD EVENT" for row in rows)


async def test_public_structural_core_mode_off_keeps_legacy_mixed_types(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setattr(performance_intel.settings, "public_structural_core_mode", False)
    monkeypatch.setattr(public_signal_surface.settings, "public_structural_core_mode", False)

    now = datetime.now(UTC)
    await _seed_opportunity_event(
        db_session,
        event_id="event_struct_core_off_key_cross",
        signal_type="KEY_CROSS",
        strength=75,
        created_at=now - timedelta(minutes=20),
    )
    await _seed_opportunity_event(
        db_session,
        event_id="event_struct_core_off_move",
        signal_type="MOVE",
        strength=80,
        created_at=now - timedelta(minutes=15),
    )
    await db_session.commit()

    token = await _register_pro_user(async_client, db_session, "struct-core-off@example.com")
    response = await async_client.get(
        "/api/v1/intel/opportunities?days=7&market=spreads&include_stale=true&limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rows = response.json()
    signal_types = {row["signal_type"] for row in rows}
    assert "KEY_CROSS" in signal_types
    assert "MOVE" in signal_types


def test_signal_serializer_and_discord_formatter_relabel_key_cross() -> None:
    signal = Signal(
        event_id="event_struct_core_label",
        market="spreads",
        signal_type="KEY_CROSS",
        direction="DOWN",
        from_value=-2.5,
        to_value=-3.0,
        from_price=-110,
        to_price=-108,
        window_minutes=10,
        books_affected=3,
        velocity_minutes=2.0,
        strength_score=78,
        created_at=datetime.now(UTC) - timedelta(minutes=2),
        metadata_json={"outcome_name": "BOS"},
    )

    payload = serialize_signal(signal, pro_user=True)
    assert payload["signal_type"] == "KEY_CROSS"
    assert payload["display_type"] == "STRUCTURAL THRESHOLD EVENT"

    game = Game(
        event_id="event_struct_core_label",
        sport_key="basketball_nba",
        commence_time=datetime.now(UTC) + timedelta(hours=1),
        home_team="BOS",
        away_team="NYK",
    )
    message = _format_alert(signal, game)
    assert "Title: STRUCTURAL THRESHOLD EVENT" in message
