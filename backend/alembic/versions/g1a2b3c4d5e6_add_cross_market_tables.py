"""add cross-market exchange tables

Revision ID: g1a2b3c4d5e6
Revises: f6a9b2c1d4e8
Create Date: 2026-02-26 17:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, None] = "e4d8f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- canonical_event_alignments ---
    op.create_table(
        "canonical_event_alignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_event_key", sa.String(length=255), nullable=False),
        sa.Column("sport", sa.String(length=100), nullable=False),
        sa.Column("league", sa.String(length=100), nullable=False),
        sa.Column("home_team", sa.String(length=200), nullable=False),
        sa.Column("away_team", sa.String(length=200), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sportsbook_event_id", sa.String(length=255), nullable=False),
        sa.Column("kalshi_market_id", sa.String(length=255), nullable=True),
        sa.Column("polymarket_market_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("canonical_event_key", name="uq_canonical_event_alignments_key"),
    )
    op.create_index("ix_canonical_event_alignments_canonical_event_key", "canonical_event_alignments", ["canonical_event_key"])
    op.create_index("ix_canonical_event_alignments_sport", "canonical_event_alignments", ["sport"])
    op.create_index("ix_canonical_event_alignments_league", "canonical_event_alignments", ["league"])
    op.create_index("ix_canonical_event_alignments_start_time", "canonical_event_alignments", ["start_time"])
    op.create_index("ix_canonical_event_alignments_sportsbook_event_id", "canonical_event_alignments", ["sportsbook_event_id"])
    op.create_index("ix_canonical_event_alignments_kalshi_market_id", "canonical_event_alignments", ["kalshi_market_id"])
    op.create_index("ix_canonical_event_alignments_polymarket_market_id", "canonical_event_alignments", ["polymarket_market_id"])

    # --- exchange_quote_events ---
    op.create_table(
        "exchange_quote_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_event_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("market_id", sa.String(length=255), nullable=False),
        sa.Column("outcome_name", sa.String(length=10), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "source", "market_id", "outcome_name", "timestamp",
            name="uq_exchange_quote_events_identity",
        ),
    )
    op.create_index("ix_exchange_quote_events_canonical_event_key", "exchange_quote_events", ["canonical_event_key"])
    op.create_index("ix_exchange_quote_events_source", "exchange_quote_events", ["source"])
    op.create_index("ix_exchange_quote_events_market_id", "exchange_quote_events", ["market_id"])
    op.create_index("ix_exchange_quote_events_outcome_name", "exchange_quote_events", ["outcome_name"])
    op.create_index("ix_exchange_quote_events_timestamp", "exchange_quote_events", ["timestamp"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_exchange_quote_events_key_source_ts_desc "
        "ON exchange_quote_events (canonical_event_key, source, timestamp DESC)"
    )

    # --- cross_market_lead_lag_events ---
    op.create_table(
        "cross_market_lead_lag_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_event_key", sa.String(length=255), nullable=False),
        sa.Column("threshold_type", sa.String(length=30), nullable=False),
        sa.Column("sportsbook_threshold_value", sa.Float(), nullable=False),
        sa.Column("exchange_probability_threshold", sa.Float(), nullable=False),
        sa.Column("lead_source", sa.String(length=20), nullable=False),
        sa.Column("sportsbook_break_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange_break_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lag_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "canonical_event_key",
            "sportsbook_threshold_value",
            "exchange_probability_threshold",
            name="uq_cross_market_lead_lag_identity",
        ),
    )
    op.create_index("ix_cross_market_lead_lag_events_canonical_event_key", "cross_market_lead_lag_events", ["canonical_event_key"])


def downgrade() -> None:
    op.drop_index("ix_cross_market_lead_lag_events_canonical_event_key", table_name="cross_market_lead_lag_events")
    op.drop_table("cross_market_lead_lag_events")

    op.execute("DROP INDEX IF EXISTS ix_exchange_quote_events_key_source_ts_desc")
    op.drop_index("ix_exchange_quote_events_timestamp", table_name="exchange_quote_events")
    op.drop_index("ix_exchange_quote_events_outcome_name", table_name="exchange_quote_events")
    op.drop_index("ix_exchange_quote_events_market_id", table_name="exchange_quote_events")
    op.drop_index("ix_exchange_quote_events_source", table_name="exchange_quote_events")
    op.drop_index("ix_exchange_quote_events_canonical_event_key", table_name="exchange_quote_events")
    op.drop_table("exchange_quote_events")

    op.drop_index("ix_canonical_event_alignments_polymarket_market_id", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_kalshi_market_id", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_sportsbook_event_id", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_start_time", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_league", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_sport", table_name="canonical_event_alignments")
    op.drop_index("ix_canonical_event_alignments_canonical_event_key", table_name="canonical_event_alignments")
    op.drop_table("canonical_event_alignments")
