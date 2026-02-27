"""Context score — cross-market alignment between sportsbooks and prediction exchanges.

Scores how well sportsbook line movements align with exchange (Kalshi/Polymarket)
probability movements. High alignment = markets agree = higher confidence context.
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.cross_market_divergence_event import CrossMarketDivergenceEvent
from app.models.cross_market_lead_lag_event import CrossMarketLeadLagEvent
from app.models.exchange_quote_event import ExchangeQuoteEvent

logger = logging.getLogger(__name__)


async def get_cross_market_context(db: AsyncSession, event_id: str) -> dict:
    """Compute cross-market context score for a sportsbook event."""
    # Look up alignment
    alignment_stmt = select(CanonicalEventAlignment).where(
        CanonicalEventAlignment.sportsbook_event_id == event_id
    )
    alignment = (await db.execute(alignment_stmt)).scalar_one_or_none()
    if alignment is None:
        return {
            "event_id": event_id,
            "component": "cross_market",
            "status": "insufficient_data",
            "score": None,
            "notes": "No exchange alignment found for this event.",
        }

    cek = alignment.canonical_event_key
    now = datetime.now(UTC)
    lookback = now - timedelta(minutes=60)

    # Query recent divergence events
    div_stmt = (
        select(CrossMarketDivergenceEvent)
        .where(
            CrossMarketDivergenceEvent.canonical_event_key == cek,
            CrossMarketDivergenceEvent.created_at >= lookback,
        )
        .order_by(desc(CrossMarketDivergenceEvent.created_at))
        .limit(10)
    )
    div_rows = list((await db.execute(div_stmt)).scalars().all())

    # Query recent lead-lag events
    lag_stmt = (
        select(CrossMarketLeadLagEvent)
        .where(
            CrossMarketLeadLagEvent.canonical_event_key == cek,
            CrossMarketLeadLagEvent.created_at >= lookback,
        )
        .order_by(desc(CrossMarketLeadLagEvent.created_at))
        .limit(10)
    )
    lag_rows = list((await db.execute(lag_stmt)).scalars().all())

    # Query latest exchange quote freshness
    quote_stmt = (
        select(func.max(ExchangeQuoteEvent.timestamp))
        .where(ExchangeQuoteEvent.canonical_event_key == cek)
    )
    latest_quote_ts = (await db.execute(quote_stmt)).scalar_one_or_none()

    # --- Alignment component (0-40) ---
    if not div_rows:
        alignment_component = 20.0  # Neutral — no data
        latest_divergence_type = None
    else:
        latest_div = div_rows[0]
        latest_divergence_type = latest_div.divergence_type
        alignment_scores = {
            "ALIGNED": 40.0,
            "EXCHANGE_LEADS": 25.0,
            "SPORTSBOOK_LEADS": 25.0,
            "UNCONFIRMED": 18.0,
            "REVERTED": 12.0,
            "OPPOSED": 8.0,
        }
        alignment_component = alignment_scores.get(latest_div.divergence_type, 20.0)

    # --- Lead-lag consistency component (0-30) ---
    if not lag_rows:
        lag_component = 15.0  # Neutral
        avg_lag = None
        dominant_source = None
    else:
        lags = [r.lag_seconds for r in lag_rows if r.lag_seconds is not None]
        sources = [r.lead_source for r in lag_rows if r.lead_source]
        avg_lag = sum(lags) / len(lags) if lags else None
        dominant_source = max(set(sources), key=sources.count) if sources else None

        # Consistent lead source = higher score
        consistency_ratio = sources.count(dominant_source) / len(sources) if sources else 0.0
        consistency_score = min(15.0, consistency_ratio * 15.0)

        # Low lag = higher score
        if avg_lag is None:
            speed_score = 8.0
        elif avg_lag <= 60:
            speed_score = 15.0
        elif avg_lag <= 180:
            speed_score = 10.0
        elif avg_lag <= 600:
            speed_score = 5.0
        else:
            speed_score = 2.0

        lag_component = consistency_score + speed_score

    # --- Quote freshness component (0-30) ---
    if latest_quote_ts is None:
        freshness_component = 6.0
        quote_age_minutes = None
    else:
        quote_ts = latest_quote_ts if latest_quote_ts.tzinfo is not None else latest_quote_ts.replace(tzinfo=UTC)
        quote_age_minutes = (now - quote_ts).total_seconds() / 60.0
        if quote_age_minutes <= 5:
            freshness_component = 30.0
        elif quote_age_minutes <= 15:
            freshness_component = 18.0
        elif quote_age_minutes <= 30:
            freshness_component = 10.0
        else:
            freshness_component = 6.0

    score = int(round(max(0.0, min(100.0, alignment_component + lag_component + freshness_component))))

    return {
        "event_id": event_id,
        "component": "cross_market",
        "status": "computed",
        "score": score,
        "details": {
            "alignment_found": True,
            "canonical_event_key": cek,
            "divergence_type": latest_divergence_type,
            "divergence_events_count": len(div_rows),
            "lead_source": dominant_source,
            "avg_lag_seconds": round(avg_lag, 1) if avg_lag is not None else None,
            "lead_lag_events_count": len(lag_rows),
            "quote_age_minutes": round(quote_age_minutes, 1) if quote_age_minutes is not None else None,
        },
        "notes": "Cross-market alignment between sportsbooks and Kalshi exchange.",
    }
