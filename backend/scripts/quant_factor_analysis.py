import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, and_
from statistics import mean, median
from app.core.database import AsyncSessionLocal
from app.models.signal import Signal
from app.models.clv_record import ClvRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_analysis():
    logger.info("Starting quantitative factor analysis for exchange_liquidity_skew...")
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    
    async with AsyncSessionLocal() as db:
        stmt = (
            select(
                Signal.id.label("signal_id"),
                Signal.metadata_json,
                ClvRecord.entry_line,
                ClvRecord.close_line,
                ClvRecord.clv_line,
                ClvRecord.clv_prob
            )
            .select_from(Signal)
            .join(ClvRecord, Signal.id == ClvRecord.signal_id)
            .where(
                and_(
                    Signal.created_at >= thirty_days_ago,
                    ClvRecord.clv_prob.is_not(None) # Finalized
                )
            )
        )
        
        result = await db.execute(stmt)
        rows = result.all()
    
    if not rows:
        print(json.dumps([]))
        return
        
    buckets = {
        "< 0.55": [],
        "0.55-0.60": [],
        "0.60-0.65": [],
        "> 0.65": []
    }
    
    for row in rows:
        meta = row.metadata_json or {}
        skew = meta.get("exchange_liquidity_skew")
        
        if skew is not None:
            skew = float(skew)
            clv_positive = row.clv_prob > 0 if row.clv_prob is not None else False
            clv_delta = row.clv_prob if row.clv_prob is not None else 0.0
            
            data_point = {"positive": clv_positive, "delta": clv_delta}
            
            if skew < 0.55:
                buckets["< 0.55"].append(data_point)
            elif skew < 0.60:
                buckets["0.55-0.60"].append(data_point)
            elif skew <= 0.65:
                buckets["0.60-0.65"].append(data_point)
            else:
                buckets["> 0.65"].append(data_point)
                
    payload = []
    
    for bucket_name, items in buckets.items():
        if not items:
            continue
            
        total_signals = len(items)
        positives = sum(1 for x in items if x["positive"])
        deltas = [x["delta"] for x in items]
        
        payload.append({
            "bucket": bucket_name,
            "total_signals": total_signals,
            "pct_positive_clv": round((positives / total_signals) * 100.0, 2),
            "avg_clv_delta": round(mean(deltas), 4),
            "median_clv_delta": round(median(deltas), 4)
        })
        
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    asyncio.run(run_analysis())
