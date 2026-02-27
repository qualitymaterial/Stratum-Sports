"""Tests for the EventAlignmentService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.game import Game
from app.services.alignment_service import EventAlignmentService, NBA_TEAM_KALSHI_ABBREVIATIONS


@pytest.fixture
def mock_kalshi_client():
    client = MagicMock()
    client._client = AsyncMock()
    # get_events is async — must be awaitable
    client.get_events = AsyncMock(return_value={"events": []})
    return client


async def test_team_abbreviations_complete():
    """Ensure all 30 NBA teams have abbreviations."""
    assert len(NBA_TEAM_KALSHI_ABBREVIATIONS) == 30
    assert NBA_TEAM_KALSHI_ABBREVIATIONS["Denver Nuggets"] == "DEN"
    assert NBA_TEAM_KALSHI_ABBREVIATIONS["Oklahoma City Thunder"] == "OKC"


async def test_sync_no_upcoming_games(db_session, mock_kalshi_client):
    """If no games exist, sync should return 0."""
    svc = EventAlignmentService(db_session, mock_kalshi_client)
    count = await svc.sync_kalshi_alignments()
    
    assert count == 0
    mock_kalshi_client._client.get.assert_not_called()


async def test_sync_matches_events_and_upserts(db_session, mock_kalshi_client):
    """Test full matching logic and idempotent DB upserts."""
    
    # 1. Setup a mock upcoming game in the database
    now = datetime.now(UTC)
    game_time = now + timedelta(days=1)
    
    game = Game(
        event_id="test_game_123",
        sport_key="basketball_nba",
        commence_time=game_time,
        home_team="Denver Nuggets",
        away_team="Oklahoma City Thunder",
    )
    db_session.add(game)
    await db_session.commit()
    
    # 2. Setup Kalshi API mock response
    mock_kalshi_client.get_events = AsyncMock(return_value={
        "events": [
            {
                "event_ticker": "KXNBAGAME-26FEB27OKCDEN",
                "title": "Oklahoma City at Denver",
            },
            {
                "event_ticker": "KXNBAGAME-26FEB27BOSNYK",
                "title": "Boston at New York",
            }
        ]
    })

    # 3. Run sync
    svc = EventAlignmentService(db_session, mock_kalshi_client)
    count = await svc.sync_kalshi_alignments()
    
    # 4. Verify 1 alignment was created
    assert count == 1
    
    # Check DB
    stmt = select(CanonicalEventAlignment)
    alignments = (await db_session.execute(stmt)).scalars().all()
    
    assert len(alignments) == 1
    a = alignments[0]
    
    # Canonical key should be constructed as sport_away_home_date
    expected_key = f"basketball_nba_okc_den_{game_time.strftime('%Y-%m-%d')}".lower()
    
    assert a.canonical_event_key == expected_key
    assert a.sportsbook_event_id == "test_game_123"
    assert a.kalshi_market_id == "KXNBAGAME-26FEB27OKCDEN-DEN"
    assert a.home_team == "Denver Nuggets"
    assert a.away_team == "Oklahoma City Thunder"
    
    # 5. Run sync AGAIN (idempotency check)
    await svc.sync_kalshi_alignments()
    
    # SQLite / Postgres upsert might return 1 for a matched/updated row
    # The real verification is that we only have 1 row in the DB
    alignments_2 = (await db_session.execute(stmt)).scalars().all()
    assert len(alignments_2) == 1
    assert alignments_2[0].id == a.id  # Same row UUID
