import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StructuralEventVenueParticipation(Base):
    __tablename__ = "structural_event_venue_participation"
    __table_args__ = (
        UniqueConstraint(
            "structural_event_id",
            "venue",
            name="uq_structural_event_venue_participation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    structural_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("structural_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    venue: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    venue_tier: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    crossed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    line_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    line_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
