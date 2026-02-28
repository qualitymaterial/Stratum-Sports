import asyncio
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.signal import Signal

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Signal).limit(5))
        signals = result.scalars().all()
        for s in signals:
            print(f"Sig: {s.id} - {s.event_id} - {s.market} - {s.signal_type}")
        
        result2 = await db.execute(text("SELECT sport_key, COUNT(*) FROM games GROUP BY sport_key"))
        for row in result2.fetchall():
            print(f"Game count: {row}")

if __name__ == "__main__":
    asyncio.run(check())
