from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import logging
from app.core.config import get_settings
from app.models.signal import Signal
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.exchange_quote_event import ExchangeQuoteEvent

logger = logging.getLogger(__name__)

def compute_kalshi_skew_gate(skew: float | None) -> Dict[str, Any]:
    """
    Compute Kalshi liquidity skew gates.
    """
    settings = get_settings()
    
    res = {
        "kalshi_liquidity_skew": skew,
        "kalshi_gate_threshold": settings.kalshi_skew_gate_threshold,
        "kalshi_gate_mode": settings.kalshi_skew_gate_mode,
        "kalshi_skew_bucket": None,
        "kalshi_gate_pass": None,
    }
    
    if skew is None:
        return res
        
    bucket = "A: <0.55"
    if skew < 0.55:
        bucket = "A: <0.55"
    elif skew < 0.60:
        bucket = "B: 0.55-0.60"
    elif skew <= 0.65:
        bucket = "C: 0.60-0.65"
    else:
        bucket = "D: >0.65"
        
    res["kalshi_skew_bucket"] = bucket
    res["kalshi_gate_pass"] = skew >= settings.kalshi_skew_gate_threshold
    
    return res

async def attach_exchange_liquidity_skew(db: AsyncSession, signals: list[Signal]) -> None:
    """
    Fetch the latest ExchangeQuoteEvent for each signal's event_id
    and calculate the liquidity skew, updating the signal's metadata_json.
    """
    if not signals:
        return

    # 1. Get unique event IDs
    event_ids = list({s.event_id for s in signals})

    # 2. Get Canonical Event Alignments for these events
    align_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.sportsbook_event_id.in_(event_ids)
    )
    alignments = list((await db.execute(align_stmt)).scalars().all())
    
    if not alignments:
        return

    # Map sportsbook_event_id -> canonical_event_key
    event_to_cek = {a.sportsbook_event_id: a.canonical_event_key for a in alignments}
    cek_list = list(event_to_cek.values())

    # 3. Get the latest exchange quotes for these keys
    latest_prob_by_cek = {}
    for cek in cek_list:
        quote_stmt = (
            select(ExchangeQuoteEvent)
            .where(
                ExchangeQuoteEvent.canonical_event_key == cek,
                ExchangeQuoteEvent.source == "KALSHI"
            )
            .order_by(desc(ExchangeQuoteEvent.timestamp))
            .limit(1)
        )
        latest = (await db.execute(quote_stmt)).scalars().first()
        if latest:
            # Skew is the maximum probability between YES and NO
            p = latest.probability
            skew = max(p, 1.0 - p)
            latest_prob_by_cek[cek] = skew

    # 4. Attach to signals metadata
    for signal in signals:
        cek = event_to_cek.get(signal.event_id)
        if not cek:
            continue
            
        skew = latest_prob_by_cek.get(cek)
        if skew is not None:
            meta = dict(signal.metadata_json or {})
            meta["exchange_liquidity_skew"] = round(skew, 4)
            signal.metadata_json = meta
