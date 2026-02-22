"""add_clv_tables

Revision ID: f3c19b2e4d6a
Revises: d2a4f6c9b7e1
Create Date: 2026-02-21 17:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f3c19b2e4d6a"
down_revision: Union[str, None] = "d2a4f6c9b7e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "closing_consensus",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("close_line", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("close_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_id",
            "market",
            "outcome_name",
            name="uq_closing_consensus_event_market_outcome",
        ),
    )
    op.create_index("ix_closing_consensus_event_id", "closing_consensus", ["event_id"], unique=False)
    op.create_index("ix_closing_consensus_market", "closing_consensus", ["market"], unique=False)
    op.create_index("ix_closing_consensus_outcome_name", "closing_consensus", ["outcome_name"], unique=False)
    op.create_index("ix_closing_consensus_computed_at", "closing_consensus", ["computed_at"], unique=False)

    op.create_table(
        "clv_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("entry_line", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("close_line", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("clv_line", sa.Float(), nullable=True),
        sa.Column("clv_prob", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_clv_records_signal_id", "clv_records", ["signal_id"], unique=True)
    op.create_index("ix_clv_records_event_id", "clv_records", ["event_id"], unique=False)
    op.create_index("ix_clv_records_signal_type", "clv_records", ["signal_type"], unique=False)
    op.create_index("ix_clv_records_market", "clv_records", ["market"], unique=False)
    op.create_index("ix_clv_records_outcome_name", "clv_records", ["outcome_name"], unique=False)
    op.create_index("ix_clv_records_computed_at", "clv_records", ["computed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clv_records_computed_at", table_name="clv_records")
    op.drop_index("ix_clv_records_outcome_name", table_name="clv_records")
    op.drop_index("ix_clv_records_market", table_name="clv_records")
    op.drop_index("ix_clv_records_signal_type", table_name="clv_records")
    op.drop_index("ix_clv_records_event_id", table_name="clv_records")
    op.drop_index("ix_clv_records_signal_id", table_name="clv_records")
    op.drop_table("clv_records")

    op.drop_index("ix_closing_consensus_computed_at", table_name="closing_consensus")
    op.drop_index("ix_closing_consensus_outcome_name", table_name="closing_consensus")
    op.drop_index("ix_closing_consensus_market", table_name="closing_consensus")
    op.drop_index("ix_closing_consensus_event_id", table_name="closing_consensus")
    op.drop_table("closing_consensus")
