"""Cross-market lead–lag propagation events between sportsbooks and exchanges."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrossMarketLeadLagEvent(Base):
    """Records a single observed lead–lag relationship.

    One row per aligned pair of (sportsbook threshold break,
    exchange probability threshold break) for a given canonical event.
    Written once via ON CONFLICT DO NOTHING — fully idempotent.
    """

    __tablename__ = "cross_market_lead_lag_events"
    __table_args__ = (
        UniqueConstraint(
            "canonical_event_key",
            "sportsbook_threshold_value",
            "exchange_probability_threshold",
            name="uq_cross_market_lead_lag_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_event_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    threshold_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "SPREAD_THRESHOLD" | "PROBABILITY_THRESHOLD"
    sportsbook_threshold_value: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    exchange_probability_threshold: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    lead_source: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "SPORTSBOOK" | "EXCHANGE"
    sportsbook_break_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    exchange_break_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lag_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
