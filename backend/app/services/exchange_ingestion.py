"""Exchange quote ingestion service for Kalshi and Polymarket markets."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_quote_event import ExchangeQuoteEvent

logger = logging.getLogger(__name__)


class ExchangeIngestionService:
    """Normalises raw exchange payloads and appends ExchangeQuoteEvent rows.

    Ingestion is idempotent — duplicate rows (same source, market_id,
    outcome_name, timestamp) are silently skipped via ON CONFLICT DO NOTHING.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest_exchange_quotes(
        self,
        canonical_event_key: str,
        source: str,
        raw_payload: dict,
    ) -> int:
        """Parse *raw_payload*, persist quote events, return rows inserted."""
        source_upper = source.upper()
        if source_upper == "KALSHI":
            parsed = self._parse_kalshi(raw_payload)
        elif source_upper == "POLYMARKET":
            parsed = self._parse_polymarket(raw_payload)
        else:
            logger.warning(
                "Unknown exchange source; skipping",
                extra={"source": source, "canonical_event_key": canonical_event_key},
            )
            return 0

        if not parsed:
            return 0

        inserted = 0
        for row in parsed:
            values = {
                "canonical_event_key": canonical_event_key,
                "source": source_upper,
                "market_id": row["market_id"],
                "outcome_name": row["outcome_name"],
                "probability": row["probability"],
                "price": row.get("price"),
                "timestamp": row["timestamp"],
            }
            stmt = pg_insert(ExchangeQuoteEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_exchange_quote_events_identity",
            )
            result = await self.db.execute(stmt)
            if result.rowcount > 0:
                inserted += 1

        await self.db.flush()

        logger.info(
            "Exchange quotes ingested",
            extra={
                "canonical_event_key": canonical_event_key,
                "source": source_upper,
                "parsed": len(parsed),
                "inserted": inserted,
            },
        )
        return inserted

    # ------------------------------------------------------------------
    # Source-specific parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_kalshi(raw_payload: dict) -> list[dict]:
        """Normalise a Kalshi market snapshot into quote rows.

        Expected payload shape (v1)::

            {
                "market_id": "...",
                "outcomes": [
                    {"name": "YES", "probability": 0.62, "price": 0.62},
                    {"name": "NO",  "probability": 0.38, "price": 0.38},
                ],
                "timestamp": "2026-02-26T22:00:00+00:00"
            }

        The parser is defensive: missing or malformed fields cause the
        individual outcome to be skipped rather than the entire payload.
        """
        rows: list[dict] = []
        market_id = raw_payload.get("market_id")
        if not market_id:
            logger.warning("Kalshi payload missing market_id")
            return rows

        raw_ts = raw_payload.get("timestamp")
        if raw_ts is None:
            ts = datetime.now(UTC)
        elif isinstance(raw_ts, str):
            ts = _parse_iso(raw_ts)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)

        outcomes = raw_payload.get("outcomes", [])
        # Also support flat single-outcome payloads
        if not outcomes and "probability" in raw_payload:
            outcomes = [
                {
                    "name": raw_payload.get("outcome_name", "YES"),
                    "probability": raw_payload["probability"],
                    "price": raw_payload.get("price"),
                }
            ]

        for outcome in outcomes:
            name = str(outcome.get("name", "")).upper()
            if name not in {"YES", "NO"}:
                continue
            prob = outcome.get("probability")
            if prob is None:
                continue
            try:
                prob = float(prob)
            except (TypeError, ValueError):
                continue

            rows.append(
                {
                    "market_id": str(market_id),
                    "outcome_name": name,
                    "probability": prob,
                    "price": _safe_float(outcome.get("price")),
                    "timestamp": ts,
                }
            )
        return rows

    @staticmethod
    def _parse_polymarket(raw_payload: dict) -> list[dict]:
        """Normalise a Polymarket market snapshot into quote rows.

        Expected payload shape (v1)::

            {
                "market_id": "...",
                "outcomes": [
                    {"name": "YES", "probability": 0.55, "price": 0.55},
                    {"name": "NO",  "probability": 0.45, "price": 0.45},
                ],
                "timestamp": "2026-02-26T22:00:00+00:00"
            }

        Polymarket may also deliver probability as ``"outcomePrices"``
        or ``"price"`` at the top level — the parser handles both.
        """
        rows: list[dict] = []
        market_id = raw_payload.get("market_id") or raw_payload.get("condition_id")
        if not market_id:
            logger.warning("Polymarket payload missing market_id / condition_id")
            return rows

        raw_ts = raw_payload.get("timestamp")
        if raw_ts is None:
            ts = datetime.now(UTC)
        elif isinstance(raw_ts, str):
            ts = _parse_iso(raw_ts)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)

        outcomes = raw_payload.get("outcomes", [])
        if not outcomes and "probability" in raw_payload:
            outcomes = [
                {
                    "name": raw_payload.get("outcome_name", "YES"),
                    "probability": raw_payload["probability"],
                    "price": raw_payload.get("price"),
                }
            ]

        for outcome in outcomes:
            name = str(outcome.get("name", "")).upper()
            if name not in {"YES", "NO"}:
                continue
            prob = outcome.get("probability")
            if prob is None:
                continue
            try:
                prob = float(prob)
            except (TypeError, ValueError):
                continue

            rows.append(
                {
                    "market_id": str(market_id),
                    "outcome_name": name,
                    "probability": prob,
                    "price": _safe_float(outcome.get("price")),
                    "timestamp": ts,
                }
            )
        return rows


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string to timezone-aware datetime."""
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _safe_float(val: object) -> float | None:
    """Return *val* as float or None if conversion fails."""
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
