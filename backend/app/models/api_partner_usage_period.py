import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ApiPartnerUsagePeriod(Base, TimestampMixin):
    __tablename__ = "api_partner_usage_periods"
    __table_args__ = (
        UniqueConstraint("user_id", "key_id", "period_start", name="uq_usage_period_user_key_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_partner_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_meter_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", lazy="noload")
    key = relationship("ApiPartnerKey", lazy="noload")
