import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DiscordConnection(Base, TimestampMixin):
    __tablename__ = "discord_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    webhook_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_spreads: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_totals: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_multibook: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_strength: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    thresholds_json: Mapped[dict] = mapped_column("thresholds", JSONB, default=dict, nullable=False)

    user = relationship("User", back_populates="discord_connection")
