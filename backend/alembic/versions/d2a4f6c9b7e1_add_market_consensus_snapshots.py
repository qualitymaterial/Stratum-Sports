"""add_market_consensus_snapshots

Revision ID: d2a4f6c9b7e1
Revises: a6e31b95c8be
Create Date: 2026-02-21 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2a4f6c9b7e1"
down_revision: Union[str, None] = "a6e31b95c8be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_consensus_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("consensus_line", sa.Float(), nullable=True),
        sa.Column("consensus_price", sa.Float(), nullable=True),
        sa.Column("dispersion", sa.Float(), nullable=True),
        sa.Column("books_count", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_market_consensus_snapshots_event_id",
        "market_consensus_snapshots",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_consensus_snapshots_market",
        "market_consensus_snapshots",
        ["market"],
        unique=False,
    )
    op.create_index(
        "ix_market_consensus_snapshots_outcome_name",
        "market_consensus_snapshots",
        ["outcome_name"],
        unique=False,
    )
    op.create_index(
        "ix_market_consensus_snapshots_fetched_at",
        "market_consensus_snapshots",
        ["fetched_at"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX ix_market_consensus_event_market_outcome_fetched_desc "
        "ON market_consensus_snapshots (event_id, market, outcome_name, fetched_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_market_consensus_event_market_outcome_fetched_desc", table_name="market_consensus_snapshots")
    op.drop_index("ix_market_consensus_snapshots_fetched_at", table_name="market_consensus_snapshots")
    op.drop_index("ix_market_consensus_snapshots_outcome_name", table_name="market_consensus_snapshots")
    op.drop_index("ix_market_consensus_snapshots_market", table_name="market_consensus_snapshots")
    op.drop_index("ix_market_consensus_snapshots_event_id", table_name="market_consensus_snapshots")
    op.drop_table("market_consensus_snapshots")
