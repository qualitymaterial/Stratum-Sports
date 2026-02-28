"""
Actionable book card tools for the Stratum Sports MCP server.

Covers:
  - get_actionable_books       → GET /api/v1/intel/books/actionable
  - get_actionable_books_batch → GET /api/v1/intel/books/actionable/batch
"""

from __future__ import annotations

from stratum_mcp.app import mcp
from stratum_mcp.client import request


@mcp.tool()
async def get_actionable_books(
    event_id: str,
    signal_id: str,
) -> dict:
    """
    Fetch an actionable book card for a specific signal on a specific game.

    The book card identifies which sportsbooks currently have the best available
    line for a given signal, providing a direct execution roadmap.

    Args:
        event_id:  The Stratum event identifier (use list_games to get valid IDs).
        signal_id: The UUID of the signal (use get_signal_quality to get signal IDs).

    Returns:
        {"meta": {...}, "data": {
            "signal_id": str,
            "event_id": str,
            "recommended_books": [list of books with current line/price],
            "books_considered": int,
            "best_line": float,
            "best_price": float
        }}
    """
    return await request(
        "GET",
        "/api/v1/intel/books/actionable",
        params={
            "event_id": event_id,
            "signal_id": signal_id,
        },
    )


@mcp.tool()
async def get_actionable_books_batch(
    event_id: str,
    signal_ids: str,
) -> dict:
    """
    Fetch actionable book cards for multiple signals on a single game in one call.

    Efficiently retrieves book recommendations for up to 20 signals at once.

    Args:
        event_id:   The Stratum event identifier.
        signal_ids: Comma-separated list of signal UUIDs
                    (e.g. "uuid1,uuid2,uuid3"). Max 20.

    Returns:
        {"meta": {...}, "data": [list of actionable book cards, one per valid signal_id]}
    """
    # Cap the number of signal IDs to avoid huge payloads
    ids = [s.strip() for s in signal_ids.split(",") if s.strip()]
    if len(ids) > 20:
        ids = list(ids[:20])
    capped_signal_ids = ",".join(ids)

    return await request(
        "GET",
        "/api/v1/intel/books/actionable/batch",
        params={
            "event_id": event_id,
            "signal_ids": capped_signal_ids,
        },
    )
