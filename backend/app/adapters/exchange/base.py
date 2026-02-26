"""Protocol and shared types for exchange market adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class NormalizedQuote:
    """Typed representation of a single exchange outcome quote."""

    market_id: str
    outcome_name: str  # YES | NO
    probability: float  # 0.0–1.0
    price: float | None
    timestamp: datetime


@runtime_checkable
class ExchangeMarketClient(Protocol):
    """Interface all exchange adapter clients must satisfy."""

    async def fetch_market_quotes(self, market_id: str) -> dict:
        """Fetch current market state from the exchange.

        Returns the raw JSON-like payload as a dict.  Normalization
        is handled downstream by ExchangeIngestionService.
        """
        ...
