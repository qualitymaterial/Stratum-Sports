import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    from_value: Mapped[float] = mapped_column(Float, nullable=False)
    to_value: Mapped[float] = mapped_column(Float, nullable=False)
    from_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    books_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    velocity_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    # points-per-minute magnitude (distinct from legacy velocity_minutes)
    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    acceleration: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_bucket: Mapped[str | None] = mapped_column(String(16), nullable=True)
    composite_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_to_tip: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    strength_score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
