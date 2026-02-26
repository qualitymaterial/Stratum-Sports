"""Typed errors for exchange adapter clients."""

from __future__ import annotations


class ExchangeUpstreamError(Exception):
    """Raised when an exchange API request fails.

    Attributes:
        source: Exchange name (e.g. "KALSHI", "POLYMARKET").
        market_id: The exchange market identifier that was queried.
        reason: Human-readable error description.
    """

    def __init__(self, source: str, market_id: str, reason: str) -> None:
        self.source = source
        self.market_id = market_id
        self.reason = reason
        super().__init__(f"[{source}] market_id={market_id}: {reason}")
