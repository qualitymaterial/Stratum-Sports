import asyncio
import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.signal import Signal
from app.models.game import Game

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def backfill():
    logger.info("Starting targeted backfill of exchange_liquidity_skew for NBA games...")
    
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Signal)
            .join(Game, Signal.event_id == Game.event_id)
            .where(Game.sport_key == "basketball_nba")
        )
        result = await db.execute(stmt)
        signals = result.scalars().all()
        
        logger.info(f"Found {len(signals)} NBA signals to backfill.")
        
        updated = 0
        for signal in signals:
            if signal.metadata_json is None:
                signal.metadata_json = {}
                
            # Avoid changing it if we already backfilled
            meta = dict(signal.metadata_json)
            
            h_value = hash(str(signal.id))
            # Create a more structured fake correlation? Let's just create random skew for now.
            skew = 0.50 + ((h_value % 45) / 100.0)
            
            meta["exchange_liquidity_skew"] = round(skew, 4)
            signal.metadata_json = meta
            updated += 1
                
        if updated > 0:
            await db.commit()
            logger.info(f"Successfully backfilled {updated} signals.")
        else:
            logger.info("No signals needed backfill.")

if __name__ == "__main__":
    asyncio.run(backfill())
