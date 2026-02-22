import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClosingConsensus(Base):
    __tablename__ = "closing_consensus"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "market",
            "outcome_name",
            name="uq_closing_consensus_event_market_outcome",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    close_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
