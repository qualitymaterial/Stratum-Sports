"""Service to auto-align sportsbook games with exchange markets."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.exchange.kalshi_client import KalshiClient
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.game import Game

logger = logging.getLogger(__name__)

# Kalshi uses 3-letter abbreviations in their event tickers (e.g. KXNBAGAME-26FEB27DENOKC)
NBA_TEAM_KALSHI_ABBREVIATIONS = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


class EventAlignmentService:
    """Synchronizes canonical event alignments for upstream exchanges."""

    def __init__(self, db: AsyncSession, kalshi_client: KalshiClient) -> None:
        self.db = db
        self.kalshi_client = kalshi_client

    async def sync_kalshi_alignments(self) -> int:
        """Fetch open Kalshi events and align them to upcoming sportsbook games.
        
        Returns the number of alignments created/updated.
        """
        now = datetime.now(UTC)
        # 1. Get upcoming NBA games from the sportsbook side (up to 7 days out)
        stmt = (
            select(Game)
            .where(
                Game.commence_time >= now - timedelta(hours=6),
                Game.commence_time <= now + timedelta(days=7),
                Game.sport_key == "basketball_nba",
            )
            .order_by(Game.commence_time.asc())
        )
        games_result = await self.db.execute(stmt)
        games = list(games_result.scalars().all())

        if not games:
            logger.debug("No upcoming NBA games found for alignment")
            return 0

        # 2. Fetch open Kalshi NBA game events
        try:
            kalshi_events = await self.kalshi_client._client.get(
                "/events",
                params={"series_ticker": "KXNBAGAME", "status": "open", "limit": 100},
            )
            kalshi_events.raise_for_status()
            events_data = kalshi_events.json().get("events", [])
        except Exception as e:
            logger.error(f"Failed to fetch Kalshi events for alignment: {e}")
            return 0

        # 3. Match them up
        alignments_to_upsert: list[dict[str, Any]] = []

        for game in games:
            if not game.commence_time:
                continue
                
            away_abbrev = NBA_TEAM_KALSHI_ABBREVIATIONS.get(game.away_team)
            home_abbrev = NBA_TEAM_KALSHI_ABBREVIATIONS.get(game.home_team)
            
            if not away_abbrev or not home_abbrev:
                continue
                
            # Convert game time to US/Eastern date (Kalshi uses EST/EDT dates in tickers)
            # Kalshi format: 26FEB27 (YYMMMDD) -> 2026 Feb 27
            # Let's do a fuzzy match on the team abbreviations inside the ticker to be tolerant
            # Since an NBA event ticker is usually KXNBAGAME-YYMMMDDAWAYHOME (e.g. KXNBAGAME-26FEB27DENOKC)
            # we just check if AWAYHOME is in the ticker.
            
            target_suffix = f"{away_abbrev}{home_abbrev}"
            
            matched_event_ticker = None
            for ke in events_data:
                ticker = ke.get("event_ticker", "")
                if ticker.endswith(target_suffix):
                    matched_event_ticker = ticker
                    break
                    
            if matched_event_ticker:
                # We use the sportsbook game info to build the canonical fields
                canonical_key = f"{game.sport_key}_{away_abbrev}_{home_abbrev}_{game.commence_time.strftime('%Y-%m-%d')}".lower()
                
                alignments_to_upsert.append({
                    "canonical_event_key": canonical_key,
                    "sport": "basketball",
                    "league": "nba",
                    "home_team": game.home_team,
                    "away_team": game.away_team,
                    "start_time": game.commence_time,
                    "sportsbook_event_id": game.event_id,
                    "kalshi_market_id": matched_event_ticker,
                })

        if not alignments_to_upsert:
            return 0

        # 4. Upsert alignments cleanly
        inserted_or_updated = 0
        for data in alignments_to_upsert:
            stmt = pg_insert(CanonicalEventAlignment).values(**data)
            # On conflict, update the Kalshi market ID (and general fields just in case)
            stmt = stmt.on_conflict_do_update(
                index_elements=["canonical_event_key"],
                set_={
                    "kalshi_market_id": stmt.excluded.kalshi_market_id,
                    "start_time": stmt.excluded.start_time,
                    "sportsbook_event_id": stmt.excluded.sportsbook_event_id,
                }
            )
            res = await self.db.execute(stmt)
            if res.rowcount > 0:
                inserted_or_updated += 1

        await self.db.flush()
        
        logger.info(
            "Synced Kalshi event alignments", 
            extra={"upserted": inserted_or_updated, "games_checked": len(games)}
        )
        return inserted_or_updated
