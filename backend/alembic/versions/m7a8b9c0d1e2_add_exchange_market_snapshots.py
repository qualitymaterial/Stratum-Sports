"""add exchange_market_snapshots table

Revision ID: m7a8b9c0d1e2
Revises: 54ec1419cd2d
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "m7a8b9c0d1e2"
down_revision = "54ec1419cd2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_market_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_event_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("market_id", sa.String(length=255), nullable=False),
        sa.Column("yes_bid_probability", sa.Float(), nullable=True),
        sa.Column("yes_ask_probability", sa.Float(), nullable=True),
        sa.Column("no_bid_probability", sa.Float(), nullable=True),
        sa.Column("no_ask_probability", sa.Float(), nullable=True),
        sa.Column("yes_bid_size", sa.Integer(), nullable=True),
        sa.Column("yes_ask_size", sa.Integer(), nullable=True),
        sa.Column("no_bid_size", sa.Integer(), nullable=True),
        sa.Column("no_ask_size", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "market_id",
            "timestamp",
            name="uq_exchange_market_snapshots_identity",
        ),
    )

    op.create_index(
        "ix_exchange_market_snapshots_canonical_event_key",
        "exchange_market_snapshots",
        ["canonical_event_key"],
    )
    op.create_index(
        "ix_exchange_market_snapshots_source",
        "exchange_market_snapshots",
        ["source"],
    )
    op.create_index(
        "ix_exchange_market_snapshots_market_id",
        "exchange_market_snapshots",
        ["market_id"],
    )
    op.create_index(
        "ix_exchange_market_snapshots_timestamp",
        "exchange_market_snapshots",
        ["timestamp"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_exchange_market_snapshots_key_source_ts_desc "
        "ON exchange_market_snapshots (canonical_event_key, source, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_exchange_market_snapshots_key_source_ts_desc")
    op.drop_index("ix_exchange_market_snapshots_timestamp", table_name="exchange_market_snapshots")
    op.drop_index("ix_exchange_market_snapshots_market_id", table_name="exchange_market_snapshots")
    op.drop_index("ix_exchange_market_snapshots_source", table_name="exchange_market_snapshots")
    op.drop_index("ix_exchange_market_snapshots_canonical_event_key", table_name="exchange_market_snapshots")
    op.drop_table("exchange_market_snapshots")
