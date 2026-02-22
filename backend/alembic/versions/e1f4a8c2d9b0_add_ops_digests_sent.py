"""add_ops_digests_sent

Revision ID: e1f4a8c2d9b0
Revises: 9ab3c2d1f4e7
Create Date: 2026-02-21 21:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e1f4a8c2d9b0"
down_revision: Union[str, None] = "9ab3c2d1f4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_digests_sent",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("week_key", sa.String(length=16), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ops_digests_sent_week_key", "ops_digests_sent", ["week_key"], unique=True)
    op.create_index("ix_ops_digests_sent_sent_at", "ops_digests_sent", ["sent_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ops_digests_sent_sent_at", table_name="ops_digests_sent")
    op.drop_index("ix_ops_digests_sent_week_key", table_name="ops_digests_sent")
    op.drop_table("ops_digests_sent")
