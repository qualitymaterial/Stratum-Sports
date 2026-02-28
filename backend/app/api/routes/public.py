import logging
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.intel import PublicTeaserKpis, PublicTeaserOpportunityPoint, PublicTopAlphaCapture, PublicLiquidityHeatmap
from app.services.performance_intel import get_delayed_opportunity_teaser, get_public_teaser_kpis, get_top_alpha_capture, get_public_liquidity_heatmap

router = APIRouter()
logger = logging.getLogger(__name__)

_ALLOWED_SPORTS = {"basketball_nba", "basketball_ncaab", "americanfootball_nfl"}


def _resolve_public_sport_key(sport_key: str) -> str:
    normalized = (sport_key or "basketball_nba").strip()
    if normalized not in _ALLOWED_SPORTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported sport_key '{sport_key}'. Allowed: {','.join(sorted(_ALLOWED_SPORTS))}",
        )
    return normalized


def _ensure_public_teaser_enabled() -> None:
    settings = get_settings()
    if not settings.performance_ui_enabled or not settings.actionable_book_card_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public teaser is disabled")
    if not settings.free_teaser_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public teaser is disabled")


def _format_delta_display(row: dict) -> str:
    raw_delta = row.get("best_delta")
    if raw_delta is None:
        return "-"
    try:
        delta = float(raw_delta)
    except (TypeError, ValueError):
        return "-"

    delta_type = str(row.get("delta_type") or "line")
    if delta_type == "implied_prob":
        return f"{delta:+.3f}p"
    return f"{delta:+.2f}"


@router.get("/teaser/opportunities", response_model=list[PublicTeaserOpportunityPoint])
async def get_public_teaser_opportunities(
    response: Response,
    sport_key: str = Query("basketball_nba"),
    limit: int = Query(5, ge=1),
    db: AsyncSession = Depends(get_db),
) -> list[PublicTeaserOpportunityPoint]:
    _ensure_public_teaser_enabled()
    response.headers["Cache-Control"] = "public, s-maxage=30, stale-while-revalidate=120"

    start = perf_counter()
    resolved_sport_key = _resolve_public_sport_key(sport_key)
    normalized_limit = max(1, min(int(limit), 8))
    delay_minutes = max(15, int(get_settings().free_delay_minutes))
    rows = await get_delayed_opportunity_teaser(
        db,
        days=2,
        sport_key=resolved_sport_key,
        min_strength=max(1, int(get_settings().signal_filter_default_min_strength)),
        limit=normalized_limit,
        delay_minutes=delay_minutes,
        include_stale=False,
    )

    status_map = {"actionable": "ACTIONABLE", "monitor": "MONITOR", "stale": "STALE"}
    freshness_map = {"fresh": "Fresh", "aging": "Aging", "stale": "Stale"}
    payload = [
        PublicTeaserOpportunityPoint(
            game_label=row.get("game_label"),
            commence_time=row.get("game_commence_time"),
            signal_type=str(row.get("signal_type") or ""),
            display_type=str(row.get("display_type") or row.get("signal_type") or ""),
            market=str(row.get("market") or ""),
            outcome_name=row.get("outcome_name"),
            score_status=status_map.get(str(row.get("opportunity_status") or "").lower(), "MONITOR"),
            freshness_label=freshness_map.get(str(row.get("freshness_bucket") or "").lower(), "Stale"),
            delta_display=_format_delta_display(row),
        )
        for row in rows
    ]

    logger.info(
        "Public teaser opportunities served",
        extra={
            "sport_key": resolved_sport_key,
            "limit": normalized_limit,
            "rows": len(payload),
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return payload


@router.get("/teaser/kpis", response_model=PublicTeaserKpis)
async def get_public_teaser_kpis_view(
    response: Response,
    sport_key: str = Query("basketball_nba"),
    window_hours: int = Query(24, ge=1, le=72),
    db: AsyncSession = Depends(get_db),
) -> PublicTeaserKpis:
    _ensure_public_teaser_enabled()
    response.headers["Cache-Control"] = "public, s-maxage=30, stale-while-revalidate=120"

    start = perf_counter()
    resolved_sport_key = _resolve_public_sport_key(sport_key)
    delay_minutes = max(15, int(get_settings().free_delay_minutes))
    payload = await get_public_teaser_kpis(
        db,
        sport_key=resolved_sport_key,
        window_hours=window_hours,
        delay_minutes=delay_minutes,
    )

    logger.info(
        "Public teaser KPIs served",
        extra={
            "sport_key": resolved_sport_key,
            "window_hours": window_hours,
            "duration_ms": round((perf_counter() - start) * 1000.0, 2),
        },
    )
    return PublicTeaserKpis(**payload)


@router.get("/teaser/top-alpha", response_model=PublicTopAlphaCapture | None)
async def get_public_teaser_top_alpha(
    response: Response,
    sport_key: str = Query("basketball_nba"),
    db: AsyncSession = Depends(get_db),
) -> PublicTopAlphaCapture | None:
    _ensure_public_teaser_enabled()
    response.headers["Cache-Control"] = "public, s-maxage=30, stale-while-revalidate=120"

    resolved_sport_key = _resolve_public_sport_key(sport_key)
    row = await get_top_alpha_capture(db, sport_key=resolved_sport_key, days=2)
    if not row:
        return None

    return PublicTopAlphaCapture(**row)


@router.get("/teaser/liquidity-heatmap", response_model=PublicLiquidityHeatmap | None)
async def get_public_teaser_liquidity_heatmap(
    response: Response,
    sport_key: str = Query("basketball_nba"),
    db: AsyncSession = Depends(get_db),
) -> PublicLiquidityHeatmap | None:
    _ensure_public_teaser_enabled()
    response.headers["Cache-Control"] = "public, s-maxage=30, stale-while-revalidate=120"

    resolved_sport_key = _resolve_public_sport_key(sport_key)
    row = await get_public_liquidity_heatmap(db, sport_key=resolved_sport_key)
    if not row:
        return None

    return PublicLiquidityHeatmap(**row)
