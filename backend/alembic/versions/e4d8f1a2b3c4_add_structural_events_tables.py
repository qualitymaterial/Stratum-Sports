"""add structural events telemetry tables

Revision ID: e4d8f1a2b3c4
Revises: d9b2e1f4a6c7
Create Date: 2026-02-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e4d8f1a2b3c4"
down_revision: Union[str, None] = "d9b2e1f4a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "structural_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market_key", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("threshold_type", sa.String(length=16), nullable=False),
        sa.Column("break_direction", sa.String(length=8), nullable=False),
        sa.Column("origin_venue", sa.String(length=100), nullable=False),
        sa.Column("origin_venue_tier", sa.String(length=4), nullable=False),
        sa.Column("origin_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adoption_percentage", sa.Float(), nullable=False),
        sa.Column("adoption_count", sa.Integer(), nullable=False),
        sa.Column("active_venue_count", sa.Integer(), nullable=False),
        sa.Column("time_to_consensus_seconds", sa.Integer(), nullable=False),
        sa.Column("dispersion_pre", sa.Float(), nullable=True),
        sa.Column("dispersion_post", sa.Float(), nullable=True),
        sa.Column("break_hold_minutes", sa.Float(), nullable=True),
        sa.Column("reversal_detected", sa.Boolean(), nullable=False),
        sa.Column("reversal_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "event_id",
            "market_key",
            "outcome_name",
            "threshold_value",
            "break_direction",
            name="uq_structural_events_identity",
        ),
    )
    op.create_index("ix_structural_events_event_id", "structural_events", ["event_id"])
    op.create_index("ix_structural_events_market_key", "structural_events", ["market_key"])
    op.create_index("ix_structural_events_outcome_name", "structural_events", ["outcome_name"])
    op.create_index("ix_structural_events_threshold_type", "structural_events", ["threshold_type"])
    op.create_index("ix_structural_events_break_direction", "structural_events", ["break_direction"])
    op.create_index("ix_structural_events_origin_timestamp", "structural_events", ["origin_timestamp"])
    op.create_index("ix_structural_events_confirmation_timestamp", "structural_events", ["confirmation_timestamp"])
    op.create_index("ix_structural_events_created_at", "structural_events", ["created_at"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_structural_events_event_market_outcome_confirmation_desc "
        "ON structural_events (event_id, market_key, outcome_name, confirmation_timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_structural_events_event_created_desc "
        "ON structural_events (event_id, created_at DESC)"
    )

    op.create_table(
        "structural_event_venue_participation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("structural_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market_key", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("venue", sa.String(length=100), nullable=False),
        sa.Column("venue_tier", sa.String(length=4), nullable=False),
        sa.Column("crossed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("line_before", sa.Float(), nullable=True),
        sa.Column("line_after", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["structural_event_id"],
            ["structural_events.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "structural_event_id",
            "venue",
            name="uq_structural_event_venue_participation",
        ),
    )
    op.create_index(
        "ix_structural_event_venue_participation_structural_event_id",
        "structural_event_venue_participation",
        ["structural_event_id"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_event_id",
        "structural_event_venue_participation",
        ["event_id"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_market_key",
        "structural_event_venue_participation",
        ["market_key"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_outcome_name",
        "structural_event_venue_participation",
        ["outcome_name"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_venue",
        "structural_event_venue_participation",
        ["venue"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_venue_tier",
        "structural_event_venue_participation",
        ["venue_tier"],
    )
    op.create_index(
        "ix_structural_event_venue_participation_crossed_at",
        "structural_event_venue_participation",
        ["crossed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_structural_event_venue_participation_crossed_at",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_venue_tier",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_venue",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_outcome_name",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_market_key",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_event_id",
        table_name="structural_event_venue_participation",
    )
    op.drop_index(
        "ix_structural_event_venue_participation_structural_event_id",
        table_name="structural_event_venue_participation",
    )
    op.drop_table("structural_event_venue_participation")

    op.execute("DROP INDEX IF EXISTS ix_structural_events_event_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_structural_events_event_market_outcome_confirmation_desc")
    op.drop_index("ix_structural_events_created_at", table_name="structural_events")
    op.drop_index("ix_structural_events_confirmation_timestamp", table_name="structural_events")
    op.drop_index("ix_structural_events_origin_timestamp", table_name="structural_events")
    op.drop_index("ix_structural_events_break_direction", table_name="structural_events")
    op.drop_index("ix_structural_events_threshold_type", table_name="structural_events")
    op.drop_index("ix_structural_events_outcome_name", table_name="structural_events")
    op.drop_index("ix_structural_events_market_key", table_name="structural_events")
    op.drop_index("ix_structural_events_event_id", table_name="structural_events")
    op.drop_table("structural_events")
