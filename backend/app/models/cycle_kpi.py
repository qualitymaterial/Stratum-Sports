import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, desc
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CycleKpi(Base):
    __tablename__ = "cycle_kpis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    requests_used_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    events_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshots_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consensus_points_written: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signals_created_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signals_created_by_type: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    alerts_sent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alerts_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


Index("ix_cycle_kpis_started_at_desc", desc(CycleKpi.started_at))
Index("ix_cycle_kpis_created_at_desc", desc(CycleKpi.created_at))
