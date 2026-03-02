import asyncio
from sqlalchemy import select, func
from app.api.deps import get_db

async def main():
    async for db in get_db():
        from app.models.canonical_event_alignment import CanonicalEventAlignment
        from app.models.exchange_quote_event import ExchangeQuoteEvent
        from app.models.signal import Signal

        alignments = (await db.execute(select(func.count(CanonicalEventAlignment.id)))).scalar()
        quotes = (await db.execute(select(func.count(ExchangeQuoteEvent.id)))).scalar()
        sigs = (await db.execute(select(func.count(Signal.id)))).scalar()
        skew_sigs = (await db.execute(select(func.count(Signal.id)).where(Signal.kalshi_liquidity_skew.isnot(None)))).scalar()

        print(f"--- Local DB Skew/Kalshi Data ---")
        print(f"Canonical Alignments (Kalshi Mappings): {alignments}")
        print(f"Exchange Quote Events (Raw Data): {quotes}")
        print(f"Total Signals: {sigs}")
        print(f"Signals with kalshi_liquidity_skew: {skew_sigs}")

        # If quotes exist, get the last few
        if quotes > 0:
            latest = (await db.execute(
                select(ExchangeQuoteEvent).order_by(ExchangeQuoteEvent.created_at.desc()).limit(1)
            )).scalar_one()
            print(f"Latest quote: {latest.canonical_event_key} '{latest.outcome_name}' prob: {latest.probability} @ {latest.created_at}")
            
if __name__ == "__main__":
    asyncio.run(main())
