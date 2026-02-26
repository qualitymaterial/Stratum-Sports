import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QuoteMoveEvent(Base):
    __tablename__ = "quote_move_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    venue: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    venue_tier: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    old_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    minutes_to_tip: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


Index(
    "ix_quote_move_events_event_market_outcome_ts",
    QuoteMoveEvent.event_id,
    QuoteMoveEvent.market_key,
    QuoteMoveEvent.outcome_name,
    QuoteMoveEvent.timestamp,
)

Index(
    "ix_quote_move_events_event_market_venue",
    QuoteMoveEvent.event_id,
    QuoteMoveEvent.market_key,
    QuoteMoveEvent.venue,
)

Index(
    "ix_quote_move_events_event_market_outcome_ts_desc",
    QuoteMoveEvent.event_id,
    QuoteMoveEvent.market_key,
    QuoteMoveEvent.outcome_name,
    QuoteMoveEvent.timestamp.desc(),
)

Index(
    "ix_quote_move_events_venue_timestamp_desc",
    QuoteMoveEvent.venue,
    QuoteMoveEvent.timestamp.desc(),
)
