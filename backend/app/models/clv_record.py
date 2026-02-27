import uuid
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClvRecord(Base):
    __tablename__ = "clv_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entry_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clv_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clv_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
