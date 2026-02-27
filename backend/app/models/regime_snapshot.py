import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    regime_label: Mapped[str] = mapped_column(String(16), nullable=False)
    regime_probability: Mapped[float] = mapped_column(Float, nullable=False)
    transition_risk: Mapped[float] = mapped_column(Float, nullable=False)
    stability_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshots_used: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


Index(
    "ix_regime_snapshots_event_market_created_desc",
    RegimeSnapshot.event_id,
    RegimeSnapshot.market,
    desc(RegimeSnapshot.created_at),
)
