"""add quote_move_events and propagation_events tables

Revision ID: a1b2c3d4e5f6
Revises: c3f6e2a1b9d4
Create Date: 2026-02-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c3f6e2a1b9d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- quote_move_events --
    op.create_table(
        "quote_move_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market_key", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("venue", sa.String(length=100), nullable=False),
        sa.Column("venue_tier", sa.String(length=4), nullable=False),
        sa.Column("old_line", sa.Float(), nullable=True),
        sa.Column("new_line", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("old_price", sa.Float(), nullable=True),
        sa.Column("new_price", sa.Float(), nullable=True),
        sa.Column("price_delta", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_to_tip", sa.Float(), nullable=True),
    )
    op.create_index("ix_quote_move_events_event_id", "quote_move_events", ["event_id"])
    op.create_index("ix_quote_move_events_market_key", "quote_move_events", ["market_key"])
    op.create_index("ix_quote_move_events_outcome_name", "quote_move_events", ["outcome_name"])
    op.create_index("ix_quote_move_events_venue", "quote_move_events", ["venue"])
    op.create_index("ix_quote_move_events_venue_tier", "quote_move_events", ["venue_tier"])
    op.create_index("ix_quote_move_events_timestamp", "quote_move_events", ["timestamp"])
    op.create_index(
        "ix_quote_move_events_event_market_outcome_ts",
        "quote_move_events",
        ["event_id", "market_key", "outcome_name", "timestamp"],
    )
    op.create_index(
        "ix_quote_move_events_event_market_venue",
        "quote_move_events",
        ["event_id", "market_key", "venue"],
    )

    # -- propagation_events --
    op.create_table(
        "propagation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market_key", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("origin_venue", sa.String(length=100), nullable=False),
        sa.Column("origin_tier", sa.String(length=4), nullable=False),
        sa.Column("origin_delta", sa.Float(), nullable=False),
        sa.Column("origin_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adoption_percent", sa.Float(), nullable=False),
        sa.Column("adoption_count", sa.Integer(), nullable=False),
        sa.Column("total_venues", sa.Integer(), nullable=False),
        sa.Column("dispersion_before", sa.Float(), nullable=True),
        sa.Column("dispersion_after", sa.Float(), nullable=True),
        sa.Column("minutes_to_tip", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_propagation_events_event_id", "propagation_events", ["event_id"])
    op.create_index("ix_propagation_events_market_key", "propagation_events", ["market_key"])
    op.create_index("ix_propagation_events_outcome_name", "propagation_events", ["outcome_name"])
    op.create_index("ix_propagation_events_created_at", "propagation_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_propagation_events_created_at", table_name="propagation_events")
    op.drop_index("ix_propagation_events_outcome_name", table_name="propagation_events")
    op.drop_index("ix_propagation_events_market_key", table_name="propagation_events")
    op.drop_index("ix_propagation_events_event_id", table_name="propagation_events")
    op.drop_table("propagation_events")

    op.drop_index("ix_quote_move_events_event_market_venue", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_event_market_outcome_ts", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_timestamp", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_venue_tier", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_venue", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_outcome_name", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_market_key", table_name="quote_move_events")
    op.drop_index("ix_quote_move_events_event_id", table_name="quote_move_events")
    op.drop_table("quote_move_events")
