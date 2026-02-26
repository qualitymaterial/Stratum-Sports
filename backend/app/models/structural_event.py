import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StructuralEvent(Base):
    __tablename__ = "structural_events"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "market_key",
            "outcome_name",
            "threshold_value",
            "break_direction",
            name="uq_structural_events_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    break_direction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    origin_venue: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_venue_tier: Mapped[str] = mapped_column(String(4), nullable=False)
    origin_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    confirmation_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    adoption_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    adoption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_venue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_consensus_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispersion_pre: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispersion_post: Mapped[float | None] = mapped_column(Float, nullable=True)
    break_hold_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    reversal_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversal_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


Index(
    "ix_structural_events_event_market_outcome_confirmation_desc",
    StructuralEvent.event_id,
    StructuralEvent.market_key,
    StructuralEvent.outcome_name,
    StructuralEvent.confirmation_timestamp.desc(),
)

Index(
    "ix_structural_events_event_created_desc",
    StructuralEvent.event_id,
    StructuralEvent.created_at.desc(),
)
