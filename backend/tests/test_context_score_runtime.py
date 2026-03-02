import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

import app.services.context_score as context_score_module
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.game import Game
from app.models.user import User
from app.services.context_score.cross_market import get_cross_market_context
from app.services.market_data import build_game_detail


async def test_build_context_score_runs_components_serially(monkeypatch) -> None:
    state = {"active": 0}

    async def _component(name: str) -> dict:
        state["active"] += 1
        assert state["active"] == 1, "context components executed concurrently"
        await asyncio.sleep(0)
        state["active"] -= 1
        return {"component": name, "status": "computed", "score": 50}

    async def _injury(_db, _event_id):
        return await _component("injuries")

    async def _props(_db, _event_id):
        return await _component("player_props")

    async def _pace(_db, _event_id):
        return await _component("pace")

    async def _cross(_db, _event_id):
        return await _component("cross_market")

    monkeypatch.setattr(context_score_module, "get_injury_context", _injury)
    monkeypatch.setattr(context_score_module, "get_player_props_context", _props)
    monkeypatch.setattr(context_score_module, "get_pace_context", _pace)
    monkeypatch.setattr(context_score_module, "get_cross_market_context", _cross)

    result = await context_score_module.build_context_score(object(), "evt-serial")
    assert result["event_id"] == "evt-serial"
    assert [c["component"] for c in result["components"]] == [
        "injuries",
        "player_props",
        "pace",
        "cross_market",
    ]


async def test_cross_market_context_tolerates_duplicate_alignments(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event_id = "evt-duplicate-alignment"
    common = {
        "sport": "basketball",
        "league": "nba",
        "home_team": "Boston Celtics",
        "away_team": "Philadelphia 76ers",
        "start_time": now + timedelta(hours=2),
        "sportsbook_event_id": event_id,
    }
    db_session.add(
        CanonicalEventAlignment(
            canonical_event_key="cek-old",
            created_at=now - timedelta(minutes=5),
            updated_at=now - timedelta(minutes=5),
            **common,
        )
    )
    db_session.add(
        CanonicalEventAlignment(
            canonical_event_key="cek-new",
            created_at=now,
            updated_at=now,
            **common,
        )
    )
    await db_session.commit()

    result = await get_cross_market_context(db_session, event_id)
    assert result["status"] == "computed"
    assert result["details"]["canonical_event_key"] == "cek-new"


async def test_game_detail_falls_back_when_context_score_fails(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    event_id = "evt-context-fallback"
    user = User(email="context-fallback@example.com", password_hash="x", tier="free")
    game = Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=now + timedelta(hours=2),
        home_team="Boston Celtics",
        away_team="Philadelphia 76ers",
    )
    db_session.add(user)
    db_session.add(game)
    await db_session.commit()

    async def _boom(_db, _event_id: str) -> dict:
        raise RuntimeError("forced context failure")

    import app.services.market_data as market_data_module

    monkeypatch.setattr(market_data_module, "build_context_score", _boom)

    detail = await build_game_detail(db_session, user, event_id)
    assert detail is not None
    assert detail["event_id"] == event_id
    assert detail["context_scaffold"]["status"] == "error"
    assert detail["context_scaffold"]["components"] == []
