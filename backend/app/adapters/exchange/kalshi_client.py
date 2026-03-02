"""Kalshi exchange adapter client."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.adapters.exchange.errors import ExchangeUpstreamError
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class KalshiClient:
    """Fetches current market state from the Kalshi REST API.

    Configuration is read from the application Settings object:
    - ``kalshi_api_key``: optional API key for authenticated requests.
    - ``kalshi_base_url``: base URL for the Kalshi API.
    - ``kalshi_timeout_seconds``: per-request timeout.

    If ``kalshi_api_key`` is empty and the endpoint requires auth,
    a RuntimeError is raised at call time (fail-fast, not at import).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.kalshi_api_key
        self._base_url: str = settings.kalshi_base_url.rstrip("/")
        self._timeout: float = settings.kalshi_timeout_seconds

    async def fetch_market_quotes(self, market_id: str) -> dict:
        """Fetch current market state for *market_id* from Kalshi.

        Returns the raw JSON payload as a dict.
        Raises ExchangeUpstreamError on network/HTTP errors.
        """
        url = f"{self._base_url}/trade-api/v2/markets/{market_id}"
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning(
                "Kalshi request timed out",
                extra={"market_id": market_id, "timeout": self._timeout},
            )
            raise ExchangeUpstreamError("KALSHI", market_id, f"Timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Kalshi request failed",
                extra={"market_id": market_id, "error": str(exc)},
            )
            raise ExchangeUpstreamError("KALSHI", market_id, str(exc)) from exc

        if response.status_code != 200:
            body_snippet = response.text[:200]
            logger.warning(
                "Kalshi non-200 response",
                extra={
                    "market_id": market_id,
                    "status": response.status_code,
                    "body_snippet": body_snippet,
                },
            )
            raise ExchangeUpstreamError(
                "KALSHI",
                market_id,
                f"HTTP {response.status_code}: {body_snippet}",
            )

        payload: dict = response.json()

        # Kalshi wraps the market object under a "market" key.
        market_data = payload.get("market", payload)

        # Normalize into the shape ExchangeIngestionService._parse_kalshi expects.
        yes_price = market_data.get("yes_price") or market_data.get("last_price")
        no_price = market_data.get("no_price")

        outcomes: list[dict] = []
        if yes_price is not None:
            outcomes.append({
                "name": "YES",
                "probability": float(yes_price) / 100 if float(yes_price) > 1 else float(yes_price),
                "price": float(yes_price) / 100 if float(yes_price) > 1 else float(yes_price),
            })
        if no_price is not None:
            outcomes.append({
                "name": "NO",
                "probability": float(no_price) / 100 if float(no_price) > 1 else float(no_price),
                "price": float(no_price) / 100 if float(no_price) > 1 else float(no_price),
            })

        # If Kalshi returns outcomes in a list form already, pass those through
        if not outcomes and "outcomes" in market_data:
            outcomes = market_data["outcomes"]

        yes_bid_prob = _probability_from_any(_first_present(market_data, "yes_bid", "yes_bid_price"))
        yes_ask_prob = _probability_from_any(_first_present(market_data, "yes_ask", "yes_ask_price"))
        no_bid_prob = _probability_from_any(_first_present(market_data, "no_bid", "no_bid_price"))
        no_ask_prob = _probability_from_any(_first_present(market_data, "no_ask", "no_ask_price"))

        yes_bid_size = _safe_int(_first_present(market_data, "yes_bid_size", "yes_bid_qty"))
        yes_ask_size = _safe_int(_first_present(market_data, "yes_ask_size", "yes_ask_qty"))
        no_bid_size = _safe_int(_first_present(market_data, "no_bid_size", "no_bid_qty"))
        no_ask_size = _safe_int(_first_present(market_data, "no_ask_size", "no_ask_qty"))

        volume = _safe_int(market_data.get("volume"))
        open_interest = _safe_int(market_data.get("open_interest"))
        snapshot_ts = _resolve_snapshot_timestamp(market_data)

        result = {
            "market_id": market_id,
            "outcomes": outcomes,
            "timestamp": snapshot_ts,
            "yes_bid_prob": yes_bid_prob,
            "yes_ask_prob": yes_ask_prob,
            "no_bid_prob": no_bid_prob,
            "no_ask_prob": no_ask_prob,
            "yes_bid_size": yes_bid_size,
            "yes_ask_size": yes_ask_size,
            "no_bid_size": no_bid_size,
            "no_ask_size": no_ask_size,
            "volume": volume,
            "open_interest": open_interest,
        }

        logger.debug(
            "Kalshi market fetched",
            extra={"market_id": market_id, "outcomes_count": len(outcomes)},
        )
        return result

    async def get_events(self, series_ticker: str, status: str = "open", limit: int = 100) -> dict:
        """Fetch general events (not just a single market) for a given series.
        
        Used by the auto-alignment service to discover Kalshi's event tickers.
        """
        url = f"{self._base_url}/trade-api/v2/events"
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        params = {"series_ticker": series_ticker, "status": status, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "Kalshi get_events failed",
                extra={"series": series_ticker, "error": str(exc)},
            )
            # Alignment service handles the exception, just raise it
            raise


def _first_present(payload: dict, *keys: str) -> object | None:
    """Return first non-None key value from payload."""
    for key in keys:
        if payload.get(key) is not None:
            return payload.get(key)
    return None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _probability_from_any(value: object) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    prob = parsed / 100.0 if parsed > 1.0 else parsed
    if 0.0 <= prob <= 1.0:
        return prob
    return None


def _resolve_snapshot_timestamp(market_data: dict) -> str:
    """Choose a best-effort quote timestamp from common Kalshi fields."""
    raw = _first_present(
        market_data,
        "timestamp",
        "updated_at",
        "last_updated",
        "last_updated_ts",
        "last_trade_time",
        "close_time",
    )
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=UTC)
        return raw.isoformat()
    return datetime.now(UTC).isoformat()
