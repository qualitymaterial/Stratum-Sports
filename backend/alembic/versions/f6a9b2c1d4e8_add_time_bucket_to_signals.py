"""add time bucket to signals

Revision ID: f6a9b2c1d4e8
Revises: c4d9f1a7e2b3
Create Date: 2026-02-25 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6a9b2c1d4e8"
down_revision: Union[str, None] = "c4d9f1a7e2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("time_bucket", sa.String(length=16), nullable=True))
    op.create_index("ix_signals_time_bucket", "signals", ["time_bucket"], unique=False)
    op.execute("CREATE INDEX ix_signals_created_at_desc_time_bucket ON signals (created_at DESC, time_bucket)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_created_at_desc_time_bucket")
    op.drop_index("ix_signals_time_bucket", table_name="signals")
    op.drop_column("signals", "time_bucket")

