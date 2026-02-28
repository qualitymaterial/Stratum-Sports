"""
Market consensus tools for the Stratum Sports MCP server.

Covers:
  - get_consensus → GET /api/v1/intel/consensus
"""

from __future__ import annotations

from typing import Literal

from stratum_mcp.app import mcp
from stratum_mcp.client import request

_MARKET = Literal["spreads", "totals", "h2h"]


@mcp.tool()
async def get_consensus(
    event_id: str,
    market: _MARKET | None = None,
) -> dict:
    """
    Fetch the latest market consensus snapshot for a specific game.

    Returns the current consensus lines and prices across all tracked sportsbooks
    for the specified event, showing where the sharp money has aggregated.

    Args:
        event_id: The Stratum event identifier (e.g. "nba_lal_gsw_2024").
                  Use list_games to discover valid event IDs.
        market:   Filter by market type. If omitted, returns all available markets.

    Returns:
        {"meta": {...}, "data": [list of consensus points with line, price, num_books]}
    """
    return await request(
        "GET",
        "/api/v1/intel/consensus",
        params={
            "event_id": event_id,
            "market": market,
        },
    )
