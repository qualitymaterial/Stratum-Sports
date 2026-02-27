import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        print("Games:")
        res = await db.execute(text("SELECT id, sport_key, commence_time, home_team, away_team FROM games ORDER BY commence_time DESC LIMIT 10"))
        games = res.fetchall()
        for g in games:
            print(f"{g.id} ({g.sport_key}) - {g.home_team} vs {g.away_team} at {g.commence_time}")
            
        print("\nAlignments:")
        res2 = await db.execute(text("SELECT sportsbook_event_id, kalshi_market_id FROM canonical_event_alignments WHERE kalshi_market_id IS NOT NULL LIMIT 5"))
        aligns = res2.fetchall()
        for a in aligns:
            print(f"{a.sportsbook_event_id} -> {a.kalshi_market_id}")

if __name__ == '__main__':
    asyncio.run(main())
