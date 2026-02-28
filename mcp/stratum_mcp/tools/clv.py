"""
CLV (Closing Line Value) analytics tools for the Stratum Sports MCP server.

Covers:
  - get_clv_records    → GET /api/v1/intel/clv
  - get_clv_summary    → GET /api/v1/intel/clv/summary
  - get_clv_recap      → GET /api/v1/intel/clv/recap
  - get_clv_scorecards → GET /api/v1/intel/clv/scorecards
"""

from __future__ import annotations

from typing import Literal

from stratum_mcp.app import mcp
from stratum_mcp.client import request

_MARKET = Literal["spreads", "totals", "h2h"]
_SIGNAL_TYPE = Literal["STEAM", "MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "EXCHANGE_DIVERGENCE"]
_SPORT_KEY = Literal[
    "basketball_nba", "basketball_ncaab", "americanfootball_nfl",
    "icehockey_nhl", "soccer_epl",
]
_GRAIN = Literal["day", "week"]


@mcp.tool()
async def get_clv_records(
    event_id: str | None = None,
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    days: int = 14,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Fetch individual CLV (Closing Line Value) records for Stratum signals.

    Each record compares the entry line at signal time to the closing line,
    providing a quantitative measure of how much edge the signal captured.

    Args:
        event_id:     Filter to a specific game (e.g. "nba_lal_gsw_2024").
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        min_strength: Minimum strength score filter.
        days:         Look-back window in days (1–90). Default: 14.
        limit:        Max records to return (1–500). Default: 100.
        offset:       Pagination offset.

    Returns:
        {"meta": {...}, "data": [list of CLV records with entry_line, close_line, clv_prob]}
    """
    if limit > 500:
        limit = 500
    return await request(
        "GET",
        "/api/v1/intel/clv",
        params={
            "event_id": event_id,
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "days": days,
            "limit": limit,
            "offset": offset,
        },
    )


@mcp.tool()
async def get_clv_summary(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    min_samples: int = 5,
    days: int = 14,
) -> dict:
    """
    Fetch an aggregated CLV performance summary grouped by signal type and market.

    Shows average CLV probability, win rates, and sample counts — useful for
    evaluating which signal categories generate the most alpha.

    Args:
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        min_strength: Minimum strength score filter.
        min_samples:  Minimum sample count per bucket (removes noise). Default: 5.
        days:         Look-back window in days (1–90). Default: 14.

    Returns:
        {"meta": {...}, "data": [list of CLV summary rows]}
    """
    return await request(
        "GET",
        "/api/v1/intel/clv/summary",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "min_samples": min_samples,
            "days": days,
        },
    )


@mcp.tool()
async def get_clv_recap(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    grain: _GRAIN = "day",
    min_strength: int | None = None,
    min_samples: int = 1,
    days: int = 14,
) -> dict:
    """
    Fetch a time-series CLV recap showing performance trends over time.

    Useful for spotting regime changes, drawdown periods, or recent alpha surges.

    Args:
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        grain:        Time granularity: "day" or "week".
        min_strength: Minimum strength score filter.
        min_samples:  Minimum sample count per period. Default: 1.
        days:         Look-back window in days (1–90). Default: 14.

    Returns:
        {"meta": {...}, "data": {"rows": [...], "summary": {...}}}
    """
    return await request(
        "GET",
        "/api/v1/intel/clv/recap",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "grain": grain,
            "min_strength": min_strength,
            "min_samples": min_samples,
            "days": days,
        },
    )


@mcp.tool()
async def get_clv_scorecards(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    min_samples: int = 10,
    days: int = 30,
) -> dict:
    """
    Fetch CLV trust scorecards — a graded assessment of signal reliability.

    Each scorecard includes a trust grade (A–F), CLV beat rate, average edge,
    and sample size for a signal-type/market combination.

    Args:
        sport_key:    Filter by sport.
        market:       Filter by market type.
        signal_type:  Filter by signal type.
        min_strength: Minimum strength score filter.
        min_samples:  Minimum sample count to be included. Default: 10.
        days:         Look-back window in days (1–90). Default: 30.

    Returns:
        {"meta": {...}, "data": [list of CLV trust scorecards]}
    """
    return await request(
        "GET",
        "/api/v1/intel/clv/scorecards",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "min_samples": min_samples,
            "days": days,
        },
    )
