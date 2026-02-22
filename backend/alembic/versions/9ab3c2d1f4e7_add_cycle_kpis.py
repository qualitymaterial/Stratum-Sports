"""add_cycle_kpis

Revision ID: 9ab3c2d1f4e7
Revises: f3c19b2e4d6a
Create Date: 2026-02-21 20:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9ab3c2d1f4e7"
down_revision: Union[str, None] = "f3c19b2e4d6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cycle_kpis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cycle_id", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requests_used_delta", sa.Integer(), nullable=True),
        sa.Column("requests_remaining", sa.Integer(), nullable=True),
        sa.Column("requests_limit", sa.Integer(), nullable=True),
        sa.Column("events_processed", sa.Integer(), nullable=True),
        sa.Column("snapshots_inserted", sa.Integer(), nullable=True),
        sa.Column("consensus_points_written", sa.Integer(), nullable=True),
        sa.Column("signals_created_total", sa.Integer(), nullable=True),
        sa.Column("signals_created_by_type", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("alerts_sent", sa.Integer(), nullable=True),
        sa.Column("alerts_failed", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_cycle_kpis_cycle_id", "cycle_kpis", ["cycle_id"], unique=True)
    op.create_index("ix_cycle_kpis_started_at", "cycle_kpis", ["started_at"], unique=False)
    op.create_index("ix_cycle_kpis_created_at", "cycle_kpis", ["created_at"], unique=False)
    op.execute("CREATE INDEX ix_cycle_kpis_started_at_desc ON cycle_kpis (started_at DESC)")
    op.execute("CREATE INDEX ix_cycle_kpis_created_at_desc ON cycle_kpis (created_at DESC)")


def downgrade() -> None:
    op.drop_index("ix_cycle_kpis_created_at_desc", table_name="cycle_kpis")
    op.drop_index("ix_cycle_kpis_started_at_desc", table_name="cycle_kpis")
    op.drop_index("ix_cycle_kpis_created_at", table_name="cycle_kpis")
    op.drop_index("ix_cycle_kpis_started_at", table_name="cycle_kpis")
    op.drop_index("ix_cycle_kpis_cycle_id", table_name="cycle_kpis")
    op.drop_table("cycle_kpis")
