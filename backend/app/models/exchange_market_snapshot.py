"""Append-only top-of-book and depth snapshots for exchange markets."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExchangeMarketSnapshot(Base):
    """Immutable market-level snapshot used for exchange microstructure metrics."""

    __tablename__ = "exchange_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "market_id",
            "timestamp",
            name="uq_exchange_market_snapshots_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_event_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    yes_bid_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    yes_ask_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_bid_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_ask_probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    yes_bid_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yes_ask_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_bid_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_ask_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


Index(
    "ix_exchange_market_snapshots_key_source_ts_desc",
    ExchangeMarketSnapshot.canonical_event_key,
    ExchangeMarketSnapshot.source,
    ExchangeMarketSnapshot.timestamp.desc(),
)
