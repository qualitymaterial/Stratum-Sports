"""Append-only ledger of exchange YES/NO probability price changes."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExchangeQuoteEvent(Base):
    """Immutable record of an exchange probability quote.

    Each row captures one observed probability for a YES or NO outcome
    on a Kalshi or Polymarket contract.  This table is append-only —
    no updates are allowed.
    """

    __tablename__ = "exchange_quote_events"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "market_id",
            "outcome_name",
            "timestamp",
            name="uq_exchange_quote_events_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_event_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # "KALSHI" | "POLYMARKET"
    market_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    outcome_name: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )  # "YES" | "NO"
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


# Composite query index for time-series lookups
Index(
    "ix_exchange_quote_events_key_source_ts_desc",
    ExchangeQuoteEvent.canonical_event_key,
    ExchangeQuoteEvent.source,
    ExchangeQuoteEvent.timestamp.desc(),
)
