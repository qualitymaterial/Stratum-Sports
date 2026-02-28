import asyncio
import httpx
from datetime import datetime, timezone
import uuid

from app.core.database import AsyncSessionLocal
from app.models.game import Game
from app.models.canonical_event_alignment import CanonicalEventAlignment

async def main():
    games_to_create = []
    alignments_to_create = []

    async with httpx.AsyncClient() as c:
        for series, sport_key in [("KXNBAGAME", "basketball_nba"), ("KXNHLGAME", "icehockey_nhl")]:
            resp = await c.get("https://api.elections.kalshi.com/trade-api/v2/events", params={"series_ticker": series, "status": "open"})
            events = resp.json().get('events', [])
            
            for ev in events[:3]: 
                event_ticker = ev['event_ticker']
                
                # Fetch markets for the event
                resp2 = await c.get("https://api.elections.kalshi.com/trade-api/v2/markets", params={"event_ticker": event_ticker})
                markets = resp2.json().get('markets', [])
                if not markets:
                    continue
                
                market = markets[-1]  # The main moneyline market
                kalshi_id = market['ticker']
                
                # Create a Game
                game_id = f"test_{sport_key}_{uuid.uuid4().hex[:8]}"
                
                home = event_ticker.split('-')[-1] if '-' in event_ticker else "Home"
                away = event_ticker.split('-')[1] if '-' in event_ticker else "Away"
                start = datetime.now(timezone.utc)
                
                games_to_create.append(
                    Game(
                        event_id=game_id,
                        sport_key=sport_key,
                        commence_time=start,
                        home_team=home,
                        away_team=away
                    )
                )
                
                # Create Alignment
                alignments_to_create.append(
                    CanonicalEventAlignment(
                        canonical_event_key=f"{sport_key}_{event_ticker}".lower().replace(" ", ""),
                        sport="basketball" if "nba" in sport_key else "hockey",
                        league="nba" if "nba" in sport_key else "nhl",
                        home_team=home,
                        away_team=away,
                        start_time=start,
                        sportsbook_event_id=game_id,
                        kalshi_market_id=kalshi_id
                    )
                )

    async with AsyncSessionLocal() as db:
        for g in games_to_create:
            db.add(g)
        for a in alignments_to_create:
            db.add(a)
        await db.commit()
        print(f"✅ Created {len(games_to_create)} fake Games mapped to real Kalshi active markets!")
        for a in alignments_to_create:
            print(f"Game: {a.sportsbook_event_id} | {a.away_team} vs {a.home_team} | KALSHI: {a.kalshi_market_id}")

if __name__ == "__main__":
    asyncio.run(main())
