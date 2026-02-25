import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ApiPartnerEntitlement(Base, TimestampMixin):
    __tablename__ = "api_partner_entitlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    api_access_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    soft_limit_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    overage_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_unit_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)

    user = relationship("User", back_populates="api_partner_entitlement", lazy="noload")
