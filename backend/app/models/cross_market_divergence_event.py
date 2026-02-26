"""Cross-market divergence events between sportsbooks and exchanges."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrossMarketDivergenceEvent(Base):
    """Append-only divergence telemetry row.

    Each row captures a detected divergence (or alignment) between
    sportsbook structural breaks and exchange probability crossings
    for a given canonical event.  Idempotent via *idempotency_key*.
    """

    __tablename__ = "cross_market_divergence_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_cross_market_divergence_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_event_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    divergence_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # ALIGNED | EXCHANGE_LEADS | SPORTSBOOK_LEADS | OPPOSED | UNCONFIRMED | REVERTED
    lead_source: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # EXCHANGE | SPORTSBOOK | NONE
    sportsbook_threshold_value: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    exchange_probability_threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    sportsbook_break_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    exchange_break_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # ALIGNED | REVERTED | TIMED_OUT | FAILED
    idempotency_key: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


# Composite query index for time-series lookups
Index(
    "ix_cross_market_divergence_key_created_desc",
    CrossMarketDivergenceEvent.canonical_event_key,
    CrossMarketDivergenceEvent.created_at.desc(),
)
