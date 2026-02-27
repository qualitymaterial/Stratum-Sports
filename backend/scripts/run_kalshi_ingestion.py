import asyncio
from unittest.mock import patch, MagicMock

from app.tasks.poller import run_polling_cycle
from app.core.database import AsyncSessionLocal

async def execute_cycle():
    print("Running poller cycle to ingest Kalshi...")
    
    # We mock ingest_odds_cycle so it thinks we just ingested the 5 games
    # and we mock settings.odds_api_key so it doesn't return early
    
    with patch("app.tasks.poller.settings.odds_api_key", "dummy"):
        # We need to get the IDs of the games we just created
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            res = await db.execute(text("SELECT event_id FROM games"))
            game_ids = [row[0] for row in res.fetchall()]
        
        # When ingest_odds_cycle is called, we return those IDs!
        with patch("app.tasks.poller.ingest_odds_cycle") as mock_odds:
            mock_odds.return_value = {
                "event_ids_updated": game_ids,
                "event_ids": game_ids
            }
            
            result = await run_polling_cycle(redis=None)
            print("Result:", result)
            
            # Now let's verify if data was saved!
            async with AsyncSessionLocal() as db:
                res = await db.execute(text("SELECT count(*) FROM exchange_quote_events WHERE source='KALSHI'"))
                count = res.scalar()
                print(f"✅ VERIFIED: We have {count} Kalshi exchange quote events in the database now!")

if __name__ == "__main__":
    asyncio.run(execute_cycle())
