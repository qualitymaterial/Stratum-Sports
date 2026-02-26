import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PropagationEvent(Base):
    __tablename__ = "propagation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    origin_venue: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_tier: Mapped[str] = mapped_column(String(4), nullable=False)
    origin_delta: Mapped[float] = mapped_column(Float, nullable=False)
    origin_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    adoption_percent: Mapped[float] = mapped_column(Float, nullable=False)
    adoption_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_venues: Mapped[int] = mapped_column(Integer, nullable=False)
    dispersion_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispersion_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    minutes_to_tip: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
