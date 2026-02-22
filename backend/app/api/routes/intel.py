from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_pro_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.clv_record import ClvRecord
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.signal import Signal
from app.models.user import User
from app.schemas.intel import ClvRecordPoint, ClvSummaryPoint, ConsensusPoint

router = APIRouter()

CANONICAL_MARKETS = {"spreads", "totals", "h2h"}


def _resolve_markets(market: str | None) -> list[str]:
    settings = get_settings()
    configured = [m for m in settings.consensus_markets_list if m in CANONICAL_MARKETS]
    if not configured:
        configured = ["spreads", "totals", "h2h"]

    if market is None:
        return configured

    if market not in configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market '{market}'. Allowed: {','.join(configured)}",
        )
    return [market]


async def _latest_consensus_rows(
    db: AsyncSession,
    *,
    event_id: str,
    markets: list[str],
) -> list[MarketConsensusSnapshot]:
    base_filters = [
        MarketConsensusSnapshot.event_id == event_id,
        MarketConsensusSnapshot.market.in_(markets),
    ]
    latest_subquery = (
        select(
            MarketConsensusSnapshot.market.label("market"),
            MarketConsensusSnapshot.outcome_name.label("outcome_name"),
            func.max(MarketConsensusSnapshot.fetched_at).label("max_fetched_at"),
        )
        .where(and_(*base_filters))
        .group_by(
            MarketConsensusSnapshot.market,
            MarketConsensusSnapshot.outcome_name,
        )
        .subquery()
    )

    stmt = (
        select(MarketConsensusSnapshot)
        .join(
            latest_subquery,
            and_(
                MarketConsensusSnapshot.event_id == event_id,
                MarketConsensusSnapshot.market == latest_subquery.c.market,
                MarketConsensusSnapshot.outcome_name == latest_subquery.c.outcome_name,
                MarketConsensusSnapshot.fetched_at == latest_subquery.c.max_fetched_at,
            ),
        )
        .order_by(
            MarketConsensusSnapshot.market.asc(),
            MarketConsensusSnapshot.outcome_name.asc(),
        )
    )

    return (await db.execute(stmt)).scalars().all()


@router.get("/consensus", response_model=list[ConsensusPoint])
async def get_consensus(
    event_id: str = Query(..., min_length=1),
    market: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ConsensusPoint]:
    markets = _resolve_markets(market)
    return await _latest_consensus_rows(db, event_id=event_id, markets=markets)


@router.get("/consensus/latest", response_model=list[ConsensusPoint])
async def get_latest_consensus(
    event_id: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ConsensusPoint]:
    markets = _resolve_markets(None)
    return await _latest_consensus_rows(db, event_id=event_id, markets=markets)


@router.get("/clv", response_model=list[ClvRecordPoint])
async def get_event_clv(
    event_id: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ClvRecordPoint]:
    stmt = (
        select(
            ClvRecord.signal_id.label("signal_id"),
            ClvRecord.event_id.label("event_id"),
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            ClvRecord.outcome_name.label("outcome_name"),
            func.coalesce(Signal.strength_score, 0).label("strength_score"),
            ClvRecord.entry_line.label("entry_line"),
            ClvRecord.entry_price.label("entry_price"),
            ClvRecord.close_line.label("close_line"),
            ClvRecord.close_price.label("close_price"),
            ClvRecord.clv_line.label("clv_line"),
            ClvRecord.clv_prob.label("clv_prob"),
            ClvRecord.computed_at.label("computed_at"),
        )
        .outerjoin(Signal, Signal.id == ClvRecord.signal_id)
        .where(ClvRecord.event_id == event_id)
        .order_by(ClvRecord.computed_at.desc())
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [ClvRecordPoint(**row) for row in rows]


@router.get("/clv/summary", response_model=list[ClvSummaryPoint])
async def get_clv_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ClvSummaryPoint]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    positive_expr = case((or_(ClvRecord.clv_line > 0, ClvRecord.clv_prob > 0), 1.0), else_=0.0)

    stmt = (
        select(
            ClvRecord.signal_type.label("signal_type"),
            ClvRecord.market.label("market"),
            func.count(ClvRecord.id).label("count"),
            (func.avg(positive_expr) * 100.0).label("pct_positive_clv"),
            func.avg(ClvRecord.clv_line).label("avg_clv_line"),
            func.avg(ClvRecord.clv_prob).label("avg_clv_prob"),
        )
        .where(ClvRecord.computed_at >= cutoff)
        .group_by(ClvRecord.signal_type, ClvRecord.market)
        .order_by(ClvRecord.signal_type.asc(), ClvRecord.market.asc())
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [
        ClvSummaryPoint(
            signal_type=row["signal_type"],
            market=row["market"],
            count=int(row["count"] or 0),
            pct_positive_clv=float(row["pct_positive_clv"] or 0.0),
            avg_clv_line=float(row["avg_clv_line"]) if row["avg_clv_line"] is not None else None,
            avg_clv_prob=float(row["avg_clv_prob"]) if row["avg_clv_prob"] is not None else None,
        )
        for row in rows
    ]
