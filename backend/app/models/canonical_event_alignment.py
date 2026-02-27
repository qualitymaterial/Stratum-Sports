"""Canonical event alignment: maps sportsbook event IDs to exchange market IDs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CanonicalEventAlignment(TimestampMixin, Base):
    """Maps a sportsbook event_id to Kalshi / Polymarket market IDs.

    The canonical_event_key is an internal key used to join across
    sportsbook and exchange data for a single real-world sporting event.
    """

    __tablename__ = "canonical_event_alignments"
    __table_args__ = (
        UniqueConstraint("canonical_event_key", name="uq_canonical_event_alignments_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_event_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    sport: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    league: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String(200), nullable=False)
    away_team: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Sportsbook mapping
    sportsbook_event_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )

    # Exchange mappings (nullable until linked)
    kalshi_market_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    polymarket_market_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
