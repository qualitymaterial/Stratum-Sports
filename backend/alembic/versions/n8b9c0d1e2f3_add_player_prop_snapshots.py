"""add player_prop_snapshots table

Revision ID: n8b9c0d1e2f3
Revises: m7a8b9c0d1e2
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "n8b9c0d1e2f3"
down_revision = "m7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_prop_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("sport_key", sa.String(length=64), nullable=False),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team", sa.String(length=120), nullable=False),
        sa.Column("away_team", sa.String(length=120), nullable=False),
        sa.Column("sportsbook_key", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("outcome_name", sa.String(length=40), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_prop_snapshots_event_id", "player_prop_snapshots", ["event_id"])
    op.create_index("ix_player_prop_snapshots_sport_key", "player_prop_snapshots", ["sport_key"])
    op.create_index("ix_player_prop_snapshots_sportsbook_key", "player_prop_snapshots", ["sportsbook_key"])
    op.create_index("ix_player_prop_snapshots_market", "player_prop_snapshots", ["market"])
    op.create_index("ix_player_prop_snapshots_player_name", "player_prop_snapshots", ["player_name"])
    op.create_index("ix_player_prop_snapshots_fetched_at", "player_prop_snapshots", ["fetched_at"])
    op.create_index(
        "ix_player_prop_snapshots_event_market_player_book_fetched",
        "player_prop_snapshots",
        ["event_id", "market", "player_name", "sportsbook_key", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_prop_snapshots_event_market_player_book_fetched",
        table_name="player_prop_snapshots",
    )
    op.drop_index("ix_player_prop_snapshots_fetched_at", table_name="player_prop_snapshots")
    op.drop_index("ix_player_prop_snapshots_player_name", table_name="player_prop_snapshots")
    op.drop_index("ix_player_prop_snapshots_market", table_name="player_prop_snapshots")
    op.drop_index("ix_player_prop_snapshots_sportsbook_key", table_name="player_prop_snapshots")
    op.drop_index("ix_player_prop_snapshots_sport_key", table_name="player_prop_snapshots")
    op.drop_index("ix_player_prop_snapshots_event_id", table_name="player_prop_snapshots")
    op.drop_table("player_prop_snapshots")
