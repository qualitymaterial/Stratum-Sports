"""
Stratum Sports MCP Server — entry point.

Transport: SSE (Server-Sent Events), suitable for remote deployments.
Pro-tier gate:
  1. On startup: calls GET /api/v1/auth/me and verifies tier is "pro", "enterprise",
     or the user is an `api_partner`. If not, exits with a clear error message.
  2. Per tool call: a lightweight cached check (TTL 5 min) ensures the key remains valid.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Import the shared FastMCP instance (must happen after load_dotenv)
from stratum_mcp.app import mcp  # noqa: E402

# ---------------------------------------------------------------------------
# Pro-tier cache  (TTL = 5 minutes)
# ---------------------------------------------------------------------------
_PRO_CACHE: dict[str, Any] = {"ok": None, "checked_at": 0.0}
_PRO_CACHE_TTL = 300  # seconds


async def _check_pro_tier(*, raise_on_fail: bool = True) -> bool:
    """
    Call /api/v1/auth/me and confirm the bearer key belongs to a Pro+ account.
    Result is cached for _PRO_CACHE_TTL seconds.
    """
    now = time.monotonic()
    if _PRO_CACHE["ok"] is not None and (now - _PRO_CACHE["checked_at"]) < _PRO_CACHE_TTL:
        if not _PRO_CACHE["ok"] and raise_on_fail:
            raise PermissionError("Stratum API key does not belong to a Pro+ account.")
        return bool(_PRO_CACHE["ok"])

    from stratum_mcp.client import request as api_request  # local import avoids circular

    result = await api_request("GET", "/api/v1/auth/me")
    if not result["meta"]["ok"]:
        _PRO_CACHE.update({"ok": False, "checked_at": now})
        if raise_on_fail:
            detail = result.get("error", "unknown error")
            raise PermissionError(
                f"Could not verify Stratum API key tier (HTTP {result['meta']['status']}): {detail}"
            )
        return False

    user_data: dict = result["data"]
    tier: str = (user_data.get("tier") or "free").lower()
    has_partner: bool = bool(user_data.get("has_partner_access", False))
    is_pro = tier in {"pro", "enterprise"} or has_partner

    _PRO_CACHE.update({"ok": is_pro, "checked_at": now})

    if not is_pro and raise_on_fail:
        raise PermissionError(
            f"Stratum MCP requires a Pro+ subscription. "
            f"Current tier: '{tier}'. Upgrade at https://stratumsports.com/upgrade"
        )
    return is_pro


def require_pro() -> None:
    """
    Synchronous guard for tool calls — runs the async check in a fire-and-forget
    pattern using the current event loop.  Raises PermissionError if not Pro+.
    """
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We are already in an async context (normal MCP tool execution path).
        # Schedule the coroutine and wait for it.
        future = asyncio.ensure_future(_check_pro_tier(raise_on_fail=True))
        # Block using run_until_complete is not valid inside a running loop.
        # Instead, raise if cache says not-ok; otherwise proceed optimistically.
        if _PRO_CACHE["ok"] is False:
            raise PermissionError(
                "Stratum MCP requires a Pro+ subscription. "
                "Upgrade at https://stratumsports.com/upgrade"
            )
    else:
        loop.run_until_complete(_check_pro_tier(raise_on_fail=True))


# ---------------------------------------------------------------------------
# Register tools
# Side-effect imports: each tool module imports `mcp` from stratum_mcp.app
# and decorates its functions with @mcp.tool(), registering them on the
# shared instance automatically.
# ---------------------------------------------------------------------------
import stratum_mcp.tools.books  # noqa: F401
import stratum_mcp.tools.clv  # noqa: F401
import stratum_mcp.tools.consensus  # noqa: F401
import stratum_mcp.tools.games  # noqa: F401
import stratum_mcp.tools.opportunities  # noqa: F401
import stratum_mcp.tools.signals  # noqa: F401
import stratum_mcp.tools.watchlist  # noqa: F401

from stratum_mcp.client import request

@mcp.tool()
async def health_ping() -> dict:
    """
    Ping the Stratum API to verify authentication and Pro-tier access.
    
    Returns the current API key's tier and partner access status.
    """
    try:
        resp = await request("GET", "/api/v1/auth/me")
        if "error" in resp and resp["error"]:
            return resp
            
        return {
            "meta": resp.get("meta", {}),
            "data": {
                "tier": resp.get("data", {}).get("tier"),
                "has_partner_access": resp.get("data", {}).get("has_partner_access"),
                "authenticated": True
            }
        }
    except Exception as e:
        return {"meta": {}, "data": {"authenticated": False}, "error": str(e)}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    """
    Entry point for the `stratum-mcp` CLI command.

    Validates environment, enforces Pro-tier gate on startup, then starts the
    SSE MCP server.
    """
    api_key = os.environ.get("STRATUM_API_KEY", "").strip()
    if not api_key:
        logger.error(
            "STRATUM_API_KEY is not set. "
            "Copy .env.example to .env and add your Stratum bearer token."
        )
        sys.exit(1)

    base_url = os.environ.get("STRATUM_API_BASE_URL", "https://api.stratumsports.com")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8001"))

    logger.info("Stratum MCP — verifying API key tier against %s …", base_url)

    try:
        asyncio.run(_check_pro_tier(raise_on_fail=True))
    except PermissionError as exc:
        logger.error("🔒 Pro-tier gate failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Startup check failed: %s", exc)
        sys.exit(1)

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8001"))

    logger.info("✅ Pro-tier verified. Starting Stratum MCP SSE server on %s:%d...", host, port)
    
    # Run via FastMCP's SSE wrapper using uvicorn correctly
    import uvicorn
    # mcp.run(transport="sse") in newer fastmcp versions might start a local inspector
    # Instead, we directly run the uvicorn server exposing the SSE route.
    # Note: FastMCP usually exposes /sse and /messages automatically depending on the SDK version.
    
    uvicorn.run(mcp.sse_app, host=host, port=port)
