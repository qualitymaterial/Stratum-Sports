"""
Best opportunities tool for the Stratum Sports MCP server.

Covers:
  - get_opportunities → GET /api/v1/intel/opportunities
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


@mcp.tool()
async def get_opportunities(
    sport_key: _SPORT_KEY | None = None,
    market: _MARKET | None = None,
    signal_type: _SIGNAL_TYPE | None = None,
    min_strength: int | None = None,
    min_edge: float | None = None,
    max_width: float | None = None,
    include_stale: bool = False,
    days: int = 2,
    limit: int = 10,
) -> dict:
    """
    Fetch the best current betting opportunities ranked by edge and signal conviction.

    Opportunities combine signal strength with current market pricing to surface
    the highest-value actionable plays available right now.

    Args:
        sport_key:     Filter by sport.
        market:        Filter by market type: "spreads", "totals", or "h2h".
        signal_type:   Filter by signal type.
        min_strength:  Minimum signal strength score (1–100).
        min_edge:      Minimum calculated edge (e.g. 0.02 for 2%).
        max_width:     Maximum bid/ask spread width (tighter = more liquid).
        include_stale: Include opportunities with stale pricing data. Default: False.
        days:          Look-back window in days (1–30). Default: 2.
        limit:         Max results to return (1–50). Default: 10.

    Returns:
        {"meta": {...}, "data": [ranked list of opportunities with edge, books, signal info]}
    """
    if limit > 50:
        limit = 50
    return await request(
        "GET",
        "/api/v1/intel/opportunities",
        params={
            "sport_key": sport_key,
            "market": market,
            "signal_type": signal_type,
            "min_strength": min_strength,
            "min_edge": min_edge,
            "max_width": max_width,
            "include_stale": include_stale,
            "days": days,
            "limit": limit,
        },
    )
