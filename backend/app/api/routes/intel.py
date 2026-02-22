import logging
from datetime import datetime
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_pro_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tier import is_pro
from app.models.discord_connection import DiscordConnection
from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.models.user import User
from app.schemas.intel import (
    ActionableBookCard,
    ClvRecapResponse,
    ClvRecordPoint,
    ClvSummaryPoint,
    ClvTrustScorecard,
    ClvTeaserResponse,
    ConsensusPoint,
    SignalQualityPoint,
    SignalQualityWeeklySummary,
)
from app.services.performance_intel import (
    get_actionable_book_card,
    get_actionable_book_cards_batch,
    get_clv_postgame_recap,
    get_clv_performance_summary,
    get_clv_records_filtered,
    get_clv_trust_scorecards,
    get_clv_teaser,
    get_signal_quality_rows,
    get_signal_quality_weekly_summary,
)

router = APIRouter()
logger = logging.getLogger(__name__)

CANONICAL_MARKETS = {"spreads", "totals", "h2h"}
CANONICAL_SIGNAL_TYPES = {"MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "STEAM"}
CANONICAL_RECAP_GRAINS = {"day", "week"}


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


def _resolve_signal_type(signal_type: str | None) -> str | None:
    if signal_type is None:
        return None
    normalized = signal_type.strip().upper()
    if normalized not in CANONICAL_SIGNAL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported signal_type '{signal_type}'. Allowed: {','.join(sorted(CANONICAL_SIGNAL_TYPES))}",
        )
    return normalized


def _resolve_single_market(market: str | None) -> str | None:
    if market is None:
        return None
    resolved = _resolve_markets(market)
    return resolved[0] if resolved else None


def _resolve_recap_grain(grain: str) -> str:
    normalized = grain.strip().lower()
    if normalized not in CANONICAL_RECAP_GRAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported grain '{grain}'. Allowed: day,week",
        )
    return normalized


def _parse_signal_ids_csv(signal_ids: str) -> list[UUID]:
    parsed: list[UUID] = []
    for raw in signal_ids.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            parsed.append(UUID(token))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid signal_id '{token}'",
            ) from exc
    if not parsed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="signal_ids is required")
    return parsed


def _ensure_performance_enabled() -> None:
    if not get_settings().performance_ui_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Performance intel is disabled")


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


async def _load_discord_connection(db: AsyncSession, user_id) -> DiscordConnection | None:
    stmt = select(DiscordConnection).where(DiscordConnection.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


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
    event_id: str | None = Query(None, min_length=1),
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_strength: int | None = Query(None, ge=1, le=100),
    days: int = Query(get_settings().performance_default_days, ge=1, le=90),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ClvRecordPoint]:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    rows = await get_clv_records_filtered(
        db,
        days=days,
        event_id=event_id,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_strength=min_strength,
        limit=limit,
        offset=offset,
    )
    logger.info(
        "Intel CLV records query served",
        extra={
            "event_id": event_id,
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "days": days,
            "limit": limit,
            "offset": offset,
            "rows": len(rows),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return [ClvRecordPoint(**row) for row in rows]


@router.get("/clv/summary", response_model=list[ClvSummaryPoint])
async def get_clv_summary(
    days: int = Query(get_settings().performance_default_days, ge=1, le=90),
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_samples: int = Query(1, ge=1, le=10000),
    min_strength: int | None = Query(None, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ClvSummaryPoint]:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    rows = await get_clv_performance_summary(
        db,
        days=days,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_samples=min_samples,
        min_strength=min_strength,
    )
    logger.info(
        "Intel CLV summary query served",
        extra={
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "days": days,
            "min_samples": min_samples,
            "rows": len(rows),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return [ClvSummaryPoint(**row) for row in rows]


@router.get("/clv/recap", response_model=ClvRecapResponse)
async def get_clv_recap(
    days: int = Query(get_settings().performance_default_days, ge=1, le=90),
    grain: str = Query("day"),
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_samples: int = Query(1, ge=1, le=10000),
    min_strength: int | None = Query(None, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> ClvRecapResponse:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    resolved_grain = _resolve_recap_grain(grain)

    payload = await get_clv_postgame_recap(
        db,
        days=days,
        grain=resolved_grain,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_samples=min_samples,
        min_strength=min_strength,
    )
    logger.info(
        "Intel CLV recap query served",
        extra={
            "days": days,
            "grain": resolved_grain,
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "min_samples": min_samples,
            "rows": len(payload["rows"]),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return ClvRecapResponse(**payload)


@router.get("/clv/scorecards", response_model=list[ClvTrustScorecard])
async def get_clv_scorecards(
    days: int = Query(get_settings().performance_default_days, ge=1, le=90),
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_samples: int = Query(10, ge=1, le=10000),
    min_strength: int | None = Query(None, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ClvTrustScorecard]:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    rows = await get_clv_trust_scorecards(
        db,
        days=days,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_samples=min_samples,
        min_strength=min_strength,
    )
    logger.info(
        "Intel CLV trust scorecards query served",
        extra={
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "days": days,
            "min_samples": min_samples,
            "rows": len(rows),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return [ClvTrustScorecard(**row) for row in rows]


@router.get("/clv/teaser", response_model=ClvTeaserResponse)
async def get_clv_teaser_view(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClvTeaserResponse:
    _ensure_performance_enabled()
    settings = get_settings()
    if not settings.free_teaser_enabled and not is_pro(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teaser endpoint disabled")

    start = perf_counter()
    payload = await get_clv_teaser(db, days=days)
    logger.info(
        "Intel CLV teaser query served",
        extra={
            "days": days,
            "rows": len(payload["rows"]),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return ClvTeaserResponse(**payload)


@router.get("/signals/quality", response_model=list[SignalQualityPoint])
async def get_signal_quality(
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_strength: int | None = Query(None, ge=1, le=100),
    min_books_affected: int | None = Query(None, ge=1, le=100),
    max_dispersion: float | None = Query(None, ge=0),
    window_minutes_max: int | None = Query(None, ge=1, le=240),
    created_after: datetime | None = Query(None),
    days: int = Query(get_settings().performance_default_days, ge=1, le=90),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    apply_alert_rules: bool = Query(True),
    include_hidden: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_pro_user),
) -> list[SignalQualityPoint]:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    connection = await _load_discord_connection(db, user.id) if apply_alert_rules else None
    rows = await get_signal_quality_rows(
        db,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_strength=min_strength,
        min_books_affected=min_books_affected,
        max_dispersion=max_dispersion,
        window_minutes_max=window_minutes_max,
        created_after=created_after,
        days=days,
        limit=limit,
        offset=offset,
        apply_alert_rules=apply_alert_rules,
        include_hidden=include_hidden,
        connection=connection,
    )
    logger.info(
        "Intel signal quality query served",
        extra={
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "days": days,
            "min_strength": min_strength,
            "apply_alert_rules": apply_alert_rules,
            "include_hidden": include_hidden,
            "rows": len(rows),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return [SignalQualityPoint(**row) for row in rows]


@router.get("/signals/weekly-summary", response_model=SignalQualityWeeklySummary)
async def get_signal_quality_weekly(
    days: int = Query(7, ge=1, le=30),
    signal_type: str | None = Query(None),
    market: str | None = Query(None),
    min_strength: int | None = Query(None, ge=1, le=100),
    apply_alert_rules: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_pro_user),
) -> SignalQualityWeeklySummary:
    _ensure_performance_enabled()
    start = perf_counter()
    resolved_market = _resolve_single_market(market)
    resolved_signal_type = _resolve_signal_type(signal_type)
    connection = await _load_discord_connection(db, user.id) if apply_alert_rules else None
    payload = await get_signal_quality_weekly_summary(
        db,
        days=days,
        signal_type=resolved_signal_type,
        market=resolved_market,
        min_strength=min_strength,
        apply_alert_rules=apply_alert_rules,
        connection=connection,
    )
    logger.info(
        "Intel signal quality weekly summary served",
        extra={
            "days": days,
            "signal_type": resolved_signal_type,
            "market": resolved_market,
            "apply_alert_rules": apply_alert_rules,
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return SignalQualityWeeklySummary(**payload)


@router.get("/books/actionable", response_model=ActionableBookCard)
async def get_actionable_books(
    event_id: str = Query(..., min_length=1),
    signal_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> ActionableBookCard:
    settings = get_settings()
    if not settings.actionable_book_card_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actionable book card is disabled")

    start = perf_counter()
    payload = await get_actionable_book_card(
        db,
        event_id=event_id,
        signal_id=signal_id,
        max_books=settings.actionable_book_max_books,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found for event")

    logger.info(
        "Intel actionable book card served",
        extra={
            "event_id": event_id,
            "signal_id": str(signal_id),
            "books_considered": payload["books_considered"],
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return ActionableBookCard(**payload)


@router.get("/books/actionable/batch", response_model=list[ActionableBookCard])
async def get_actionable_books_batch(
    event_id: str = Query(..., min_length=1),
    signal_ids: str = Query(..., min_length=1, description="Comma-separated signal UUIDs"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_pro_user),
) -> list[ActionableBookCard]:
    settings = get_settings()
    if not settings.actionable_book_card_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actionable book card is disabled")

    parsed_signal_ids = _parse_signal_ids_csv(signal_ids)
    start = perf_counter()
    payloads = await get_actionable_book_cards_batch(
        db,
        event_id=event_id,
        signal_ids=parsed_signal_ids,
        max_books=settings.actionable_book_max_books,
    )
    logger.info(
        "Intel actionable book card batch served",
        extra={
            "event_id": event_id,
            "signal_ids_requested": len(parsed_signal_ids),
            "cards_returned": len(payloads),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return [ActionableBookCard(**payload) for payload in payloads]
