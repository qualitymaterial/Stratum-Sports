import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TeaserInteractionEvent(Base):
    __tablename__ = "teaser_interaction_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sport_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


Index(
    "ix_teaser_interaction_events_created_event_sport",
    TeaserInteractionEvent.created_at.desc(),
    TeaserInteractionEvent.event_name,
    TeaserInteractionEvent.sport_key,
)
