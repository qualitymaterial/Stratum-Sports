"""
Watchlist tool for the Stratum Sports MCP server.

Covers:
  - list_watchlist → GET /api/v1/watchlist
"""

from __future__ import annotations

from typing import Literal

from stratum_mcp.app import mcp
from stratum_mcp.client import request

_SPORT_KEY = Literal["basketball_nba", "basketball_ncaab", "americanfootball_nfl"]


@mcp.tool()
async def list_watchlist(
    sport_key: _SPORT_KEY | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Fetch the current authenticated user's watchlist.

    Returns all games the API key owner has bookmarked, along with game metadata
    (teams, sport, tip-off time). Useful for building personalized monitoring flows.

    Args:
        sport_key: Filter watchlist to a specific sport. If omitted, returns all sports.

    Returns:
        {"meta": {...}, "data": [list of watchlisted games with event_id, teams, commence_time]}
    """
    if limit > 100:
        limit = 100
    return await request(
        "GET",
        "/api/v1/watchlist",
        params={
            "sport_key": sport_key,
            "limit": limit,
            "offset": offset,
        },
    )
