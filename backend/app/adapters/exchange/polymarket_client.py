"""Polymarket exchange adapter client."""

from __future__ import annotations

import logging

import httpx

from app.adapters.exchange.errors import ExchangeUpstreamError
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Fetches current market state from the Polymarket CLOB API.

    Configuration is read from the application Settings object:
    - ``polymarket_base_url``: base URL for the Polymarket CLOB API.
    - ``polymarket_timeout_seconds``: per-request timeout.

    This adapter is disabled by default via ``ENABLE_POLYMARKET_INGEST=false``.
    The poller will not instantiate this client unless the flag is true.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url: str = settings.polymarket_base_url.rstrip("/")
        self._timeout: float = settings.polymarket_timeout_seconds

    async def fetch_market_quotes(self, market_id: str) -> dict:
        """Fetch current market state for *market_id* from Polymarket.

        Returns the raw JSON payload as a dict.
        Raises ExchangeUpstreamError on network/HTTP errors.
        """
        url = f"{self._base_url}/markets/{market_id}"
        headers: dict[str, str] = {"Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning(
                "Polymarket request timed out",
                extra={"market_id": market_id, "timeout": self._timeout},
            )
            raise ExchangeUpstreamError("POLYMARKET", market_id, f"Timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Polymarket request failed",
                extra={"market_id": market_id, "error": str(exc)},
            )
            raise ExchangeUpstreamError("POLYMARKET", market_id, str(exc)) from exc

        if response.status_code != 200:
            body_snippet = response.text[:200]
            logger.warning(
                "Polymarket non-200 response",
                extra={
                    "market_id": market_id,
                    "status": response.status_code,
                    "body_snippet": body_snippet,
                },
            )
            raise ExchangeUpstreamError(
                "POLYMARKET",
                market_id,
                f"HTTP {response.status_code}: {body_snippet}",
            )

        payload: dict = response.json()

        # Polymarket may nest under "market" or return flat
        market_data = payload.get("market", payload)

        # Normalize into shape ExchangeIngestionService._parse_polymarket expects.
        outcomes: list[dict] = []

        # Handle outcomePrices array (Polymarket format: ["0.65", "0.35"])
        outcome_prices = market_data.get("outcomePrices")
        if outcome_prices and isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
            try:
                yes_prob = float(outcome_prices[0])
                no_prob = float(outcome_prices[1])
                outcomes.append({"name": "YES", "probability": yes_prob, "price": yes_prob})
                outcomes.append({"name": "NO", "probability": no_prob, "price": no_prob})
            except (ValueError, TypeError):
                pass

        # Fallback to outcomes list
        if not outcomes and "outcomes" in market_data:
            outcomes = market_data["outcomes"]

        # Fallback to top-level probability
        if not outcomes and "probability" in market_data:
            prob = float(market_data["probability"])
            outcomes.append({"name": "YES", "probability": prob, "price": prob})

        result = {
            "market_id": market_data.get("condition_id") or market_id,
            "outcomes": outcomes,
            "timestamp": market_data.get("timestamp"),
        }

        logger.debug(
            "Polymarket market fetched",
            extra={"market_id": market_id, "outcomes_count": len(outcomes)},
        )
        return result
