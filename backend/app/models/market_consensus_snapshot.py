import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketConsensusSnapshot(Base):
    __tablename__ = "market_consensus_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    consensus_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    consensus_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispersion: Mapped[float | None] = mapped_column(Float, nullable=True)
    books_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


Index(
    "ix_market_consensus_event_market_outcome_fetched_desc",
    MarketConsensusSnapshot.event_id,
    MarketConsensusSnapshot.market,
    MarketConsensusSnapshot.outcome_name,
    desc(MarketConsensusSnapshot.fetched_at),
)
