"""Kalshi exchange adapter client."""

from __future__ import annotations

import logging

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

        result = {
            "market_id": market_id,
            "outcomes": outcomes,
            "timestamp": market_data.get("close_time") or market_data.get("timestamp"),
        }

        logger.debug(
            "Kalshi market fetched",
            extra={"market_id": market_id, "outcomes_count": len(outcomes)},
        )
        return result
