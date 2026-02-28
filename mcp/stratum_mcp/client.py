"""
Shared async HTTP client for the Stratum Sports API.

Provides a singleton ``AsyncClient`` with:
- Bearer auth
- Configurable base URL
- Timeouts (connect 5 s, read 30 s)
- Automatic retries with exponential back-off for 429 / 5xx transient errors
- A ``request()`` helper that always returns ``{"meta": {...}, "data": ...}``
  and never propagates raw stack traces to tool callers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry config
# ---------------------------------------------------------------------------
_RETRYABLE_STATUS = {429, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds; actual sleep = base * 2^attempt

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------
_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    api_key = os.environ.get("STRATUM_API_KEY", "")
    base_url = os.environ.get("STRATUM_API_BASE_URL", "https://api.stratumsports.com")
    return httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "stratum-mcp/0.1.0",
        },
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        follow_redirects=True,
    )


def get_client() -> httpx.AsyncClient:
    """Return the module-level singleton, creating it on first call."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


async def close_client() -> None:
    """Gracefully close the singleton (call from server lifespan)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Safe request helper
# ---------------------------------------------------------------------------

async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
) -> dict[str, Any]:
    """
    Execute an HTTP request against the Stratum API with retry logic.

    Returns:
        {
            "meta": {"path": str, "status": int, "ok": bool, "attempts": int},
            "data": <parsed JSON> | None,
            "error": str | None,
        }
    """
    client = get_client()
    # Strip None values from params so we don't send e.g. ?sport_key=None
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}

    last_status = 0
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.request(method, path, params=clean_params or None, json=json)
            last_status = resp.status_code

            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Stratum API retryable %s for %s — waiting %.1fs (attempt %d/%d)",
                    resp.status_code,
                    path,
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                continue

            meta = {
                "path": path,
                "status": resp.status_code,
                "ok": resp.is_success,
                "attempts": attempt + 1,
            }

            if resp.is_success:
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text
                return {"meta": meta, "data": data, "error": None}

            # Non-retryable error — surface a clean message
            try:
                err_body = resp.json()
                detail = err_body.get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"meta": meta, "data": None, "error": str(detail)}

        except httpx.TimeoutException as exc:
            logger.warning("Stratum API timeout for %s (attempt %d)", path, attempt + 1)
            if attempt == _MAX_RETRIES:
                return {
                    "meta": {"path": path, "status": 0, "ok": False, "attempts": attempt + 1},
                    "data": None,
                    "error": f"Request timed out after {_MAX_RETRIES + 1} attempts: {exc}",
                }
            await asyncio.sleep(_BACKOFF_BASE * (2**attempt))

        except httpx.RequestError as exc:
            logger.error("Stratum API request error for %s: %s", path, exc)
            return {
                "meta": {"path": path, "status": 0, "ok": False, "attempts": attempt + 1},
                "data": None,
                "error": f"Network error: {exc}",
            }

    # Exhausted retries
    return {
        "meta": {"path": path, "status": last_status, "ok": False, "attempts": _MAX_RETRIES + 1},
        "data": None,
        "error": f"Request failed after {_MAX_RETRIES + 1} attempts (last status: {last_status})",
    }
