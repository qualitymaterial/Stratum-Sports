"""add cross-market divergence events

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-02-26 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cross_market_divergence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_event_key", sa.String(length=255), nullable=False),
        sa.Column("divergence_type", sa.String(length=30), nullable=False),
        sa.Column("lead_source", sa.String(length=20), nullable=True),
        sa.Column("sportsbook_threshold_value", sa.Float(), nullable=True),
        sa.Column("exchange_probability_threshold", sa.Float(), nullable=True),
        sa.Column("sportsbook_break_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchange_break_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lag_seconds", sa.Integer(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_type", sa.String(length=20), nullable=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_cross_market_divergence_idempotency"),
    )
    op.create_index("ix_cross_market_divergence_events_canonical_event_key", "cross_market_divergence_events", ["canonical_event_key"])
    op.create_index("ix_cross_market_divergence_events_divergence_type", "cross_market_divergence_events", ["divergence_type"])
    op.create_index("ix_cross_market_divergence_events_lead_source", "cross_market_divergence_events", ["lead_source"])
    op.create_index("ix_cross_market_divergence_events_sportsbook_break_timestamp", "cross_market_divergence_events", ["sportsbook_break_timestamp"])
    op.create_index("ix_cross_market_divergence_events_exchange_break_timestamp", "cross_market_divergence_events", ["exchange_break_timestamp"])
    op.create_index("ix_cross_market_divergence_events_resolved", "cross_market_divergence_events", ["resolved"])
    op.create_index("ix_cross_market_divergence_events_resolution_type", "cross_market_divergence_events", ["resolution_type"])
    op.create_index("ix_cross_market_divergence_events_idempotency_key", "cross_market_divergence_events", ["idempotency_key"])
    op.create_index("ix_cross_market_divergence_events_created_at", "cross_market_divergence_events", ["created_at"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cross_market_divergence_key_created_desc "
        "ON cross_market_divergence_events (canonical_event_key, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cross_market_divergence_key_created_desc")
    op.drop_index("ix_cross_market_divergence_events_created_at", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_idempotency_key", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_resolution_type", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_resolved", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_exchange_break_timestamp", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_sportsbook_break_timestamp", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_lead_source", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_divergence_type", table_name="cross_market_divergence_events")
    op.drop_index("ix_cross_market_divergence_events_canonical_event_key", table_name="cross_market_divergence_events")
    op.drop_table("cross_market_divergence_events")
