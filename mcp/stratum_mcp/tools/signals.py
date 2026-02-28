"""
Signal intelligence tools for the Stratum Sports MCP server.

Covers:
  - get_signal_quality        → GET /api/v1/intel/signals/quality
  - get_signals_weekly_summary → GET /api/v1/intel/signals/weekly-summary
  - get_signal_lifecycle      → GET /api/v1/intel/signals/lifecycle
"""

from __future__ import annotations

from typing import Literal

from stratum_mcp.app import mcp
from stratum_mcp.client import request


_MARKET = Literal["spreads", "totals", "h2h"]
_SIGNAL_TYPE = Literal["STEAM", "MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "EXCHANGE_DIVERGENCE"]
_TIME_BUCKET = Literal["OPEN", "MID", "LATE", "PRETIP", "INPLAY", "UNKNOWN"]
_SPORT_KEY = Literal[
    "basketball_nba", "basketball_ncaab", "americanfootball_nfl",
    "icehockey_nhl", "soccer_epl",
]


@mcp.tool()
async def get_signal_quality(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    min_books_affected: int | None = None,
    max_dispersion: float | None = None,
    time_bucket: _TIME_BUCKET | None = None,
    days: int = 7,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Fetch Stratum signal quality records — the primary signal feed.

    Signals represent smart-money moves, steam, key-number crosses, and
    multi-book synchronizations detected by the Stratum intelligence backbone.

    Args:
        sport_key:          Filter by sport (e.g. "basketball_nba").
        market:             Filter by market type: "spreads", "totals", or "h2h".
        signal_type:        Filter by signal type (STEAM, MOVE, KEY_CROSS, etc.).
        min_strength:       Minimum strength score 1–100. Use ≥80 for high-conviction picks.
        min_books_affected: Minimum number of books that moved.
        max_dispersion:     Maximum dispersion (tighter = more consensus).
        time_bucket:        Game-time segment: OPEN, MID, LATE, PRETIP, INPLAY, UNKNOWN.
        days:               Look-back window in days (1–90). Default: 7.
        limit:              Max records to return (1–500). Default: 50.
        offset:             Pagination offset.

    Returns:
        {"meta": {...}, "data": [list of signal quality records]}
    """
    if limit > 500:
        limit = 500
    return await request(
        "GET",
        "/api/v1/intel/signals/quality",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "min_books_affected": min_books_affected,
            "max_dispersion": max_dispersion,
            "time_bucket": time_bucket,
            "days": days,
            "limit": limit,
            "offset": offset,
            "apply_alert_rules": False,
            "include_hidden": True,
        },
    )


@mcp.tool()
async def get_signals_weekly_summary(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    days: int = 7,
) -> dict:
    """
    Fetch a rolled-up weekly summary of Stratum signal quality metrics.

    Returns aggregate counts, average strength scores, success rates, and
    breakdown by signal type for the specified look-back window.

    Args:
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        min_strength: Minimum strength score filter.
        days:         Look-back window in days (1–30). Default: 7.

    Returns:
        {"meta": {...}, "data": weekly summary object}
    """
    if days > 30:
        days = 30
    return await request(
        "GET",
        "/api/v1/intel/signals/weekly-summary",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "days": days,
            "apply_alert_rules": False,
        },
    )


@mcp.tool()
async def get_signal_lifecycle(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    days: int = 7,
) -> dict:
    """
    Fetch a signal lifecycle summary showing how signals evolve from open through
    close, including timing distribution and CLV capture rates by time bucket.

    Args:
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        min_strength: Minimum strength score filter.
        days:         Look-back window in days (1–30). Default: 7.

    Returns:
        {"meta": {...}, "data": signal lifecycle summary}
    """
    if days > 30:
        days = 30
    return await request(
        "GET",
        "/api/v1/intel/signals/lifecycle",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "days": days,
            "apply_alert_rules": False,
        },
    )
