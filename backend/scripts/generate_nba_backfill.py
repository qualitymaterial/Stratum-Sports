import asyncio
import uuid
import random
import logging
from datetime import UTC, datetime, timedelta
from app.core.database import AsyncSessionLocal
from app.models.game import Game
from app.models.signal import Signal
from app.models.clv_record import ClvRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def generate_backfill():
    logger.info("Generating targeted backfill of NBA games, signals, and CLV records...")
    
    async with AsyncSessionLocal() as db:
        game_id = f"fake_nba_game_{uuid.uuid4().hex[:8]}"
        game = Game(
            id=uuid.uuid4(),
            event_id=game_id,
            sport_key="basketball_nba",
            commence_time=datetime.now(UTC) - timedelta(days=1),
            home_team="Fake Home",
            away_team="Fake Away",
            updated_at=datetime.now(UTC)
        )
        db.add(game)
        
        buckets = [
            {"count": 1250, "skew_range": (0.40, 0.549), "pos_rate": 0.51, "avg_delta": 0.0125},
            {"count": 840, "skew_range": (0.55, 0.599), "pos_rate": 0.53, "avg_delta": 0.0210},
            {"count": 415, "skew_range": (0.60, 0.649), "pos_rate": 0.57, "avg_delta": 0.0385},
            {"count": 185, "skew_range": (0.651, 0.95), "pos_rate": 0.62, "avg_delta": 0.0850},
        ]
        
        signals = []
        clv_records = []
        
        thirty_days_ago = datetime.now(UTC) - timedelta(days=20)
        
        for b in buckets:
            for _ in range(b["count"]):
                s_id = uuid.uuid4()
                skew = random.uniform(b["skew_range"][0], b["skew_range"][1])
                
                is_positive = random.random() < b["pos_rate"]
                
                if is_positive:
                    clv_val = random.uniform(0.001, b["avg_delta"] * 2.5) 
                else:
                    clv_val = random.uniform(-b["avg_delta"] * 2, -0.001) 
                
                sig = Signal(
                    id=s_id,
                    event_id=game_id,
                    market="spreads",
                    signal_type="steam",
                    direction="home",
                    from_value=-5.0,
                    to_value=-5.5,
                    from_price=-110,
                    to_price=-110,
                    window_minutes=5,
                    velocity_minutes=1.5,
                    strength_score=random.randint(50, 99),
                    created_at=thirty_days_ago + timedelta(minutes=random.randint(0, 20000)),
                    metadata_json={"exchange_liquidity_skew": skew, "outcome_name": "Fake Home"}
                )
                signals.append(sig)
                
                clv = ClvRecord(
                    id=uuid.uuid4(),
                    signal_id=s_id,
                    event_id=game_id,
                    signal_type="steam",
                    market="spreads",
                    outcome_name="Fake Home",
                    clv_prob=clv_val,
                    computed_at=sig.created_at + timedelta(hours=2)
                )
                clv_records.append(clv)
                
        # Insert signals first to satisfy FK constraint
        db.add_all(signals)
        await db.commit()
        
        db.add_all(clv_records)
        await db.commit()
        
        logger.info(f"Successfully generated {len(signals)} backfilled signals with corresponding CLV.")
        
if __name__ == "__main__":
    asyncio.run(generate_backfill())
