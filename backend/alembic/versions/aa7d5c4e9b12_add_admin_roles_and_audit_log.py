"""add admin roles and audit log

Revision ID: aa7d5c4e9b12
Revises: f6a9b2c1d4e8
Create Date: 2026-02-25 00:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "aa7d5c4e9b12"
down_revision: Union[str, None] = "f6a9b2c1d4e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("admin_role", sa.String(length=32), nullable=True))
    op.create_index("ix_users_admin_role", "users", ["admin_role"], unique=False)

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_logs_actor_user_id", "admin_audit_logs", ["actor_user_id"], unique=False)
    op.create_index("ix_admin_audit_logs_action_type", "admin_audit_logs", ["action_type"], unique=False)
    op.execute("CREATE INDEX ix_admin_audit_logs_created_at_desc ON admin_audit_logs (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_admin_audit_logs_created_at_desc")
    op.drop_index("ix_admin_audit_logs_action_type", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_actor_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_users_admin_role", table_name="users")
    op.drop_column("users", "admin_role")
