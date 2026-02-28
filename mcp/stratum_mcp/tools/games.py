"""
Game listing and detail tools for the Stratum Sports MCP server.

Covers:
  - list_games      → GET /api/v1/games
  - get_game_detail → GET /api/v1/games/{event_id}
"""

from __future__ import annotations

from typing import Literal

from stratum_mcp.app import mcp
from stratum_mcp.client import request

_SPORT_KEY = Literal["basketball_nba", "basketball_ncaab", "americanfootball_nfl"]


@mcp.tool()
async def list_games(
    sport_key: _SPORT_KEY | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    List upcoming games tracked by Stratum.

    Returns the next ~40 upcoming games (ordered by start time) with their
    event IDs, teams, sport, and tip-off time. Use event_id values from this
    response as inputs to other tools.

    Args:
        sport_key: Filter by sport. Options: "basketball_nba", "basketball_ncaab", "americanfootball_nfl".
        limit:     Max games to return (1-100). Default: 50.
        offset:    Pagination offset.

    Returns:
        {"meta": {...}, "data": [list of games with event_id, sport_key, teams, commence_time]}
    """
    if limit > 100:
        limit = 100
    return await request(
        "GET",
        "/api/v1/games",
        params={
            "sport_key": sport_key,
            "limit": limit,
            "offset": offset,
        },
    )


@mcp.tool()
async def get_game_detail(
    event_id: str,
) -> dict:
    """
    Fetch detailed market data for a specific game.

    Returns current odds, lines, consensus data, and any active signals
    for the specified event. Use list_games to get valid event IDs.

    Args:
        event_id: The Stratum event identifier (e.g. "basketball_nba_20240227_lal_gsw").

    Returns:
        {"meta": {...}, "data": full game detail including odds, signals, and consensus}
    """
    return await request(
        "GET",
        f"/api/v1/games/{event_id}",
    )
