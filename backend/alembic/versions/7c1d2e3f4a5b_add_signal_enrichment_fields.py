"""add_signal_enrichment_fields

Revision ID: 7c1d2e3f4a5b
Revises: c4d9f1a7e2b3
Create Date: 2026-02-24 15:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c1d2e3f4a5b"
down_revision: Union[str, None] = "c4d9f1a7e2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("velocity", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("acceleration", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("time_bucket", sa.String(length=16), nullable=True))
    op.add_column("signals", sa.Column("composite_score", sa.Integer(), nullable=True))
    op.add_column("signals", sa.Column("minutes_to_tip", sa.Integer(), nullable=True))
    op.add_column("signals", sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_signals_composite_score", "signals", ["composite_score"], unique=False)
    op.create_index("ix_signals_time_bucket", "signals", ["time_bucket"], unique=False)
    op.create_index(
        "ix_signals_created_at_composite_score",
        "signals",
        ["created_at", "composite_score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signals_created_at_composite_score", table_name="signals")
    op.drop_index("ix_signals_time_bucket", table_name="signals")
    op.drop_index("ix_signals_composite_score", table_name="signals")

    op.drop_column("signals", "computed_at")
    op.drop_column("signals", "minutes_to_tip")
    op.drop_column("signals", "composite_score")
    op.drop_column("signals", "time_bucket")
    op.drop_column("signals", "acceleration")
    op.drop_column("signals", "velocity")
