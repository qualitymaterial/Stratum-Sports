"""add admin MFA fields and mfa_backup_codes table

Revision ID: l6f7g8h9i0j1
Revises: k5e6f7g8h9i0
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "l6f7g8h9i0j1"
down_revision = "k5e6f7g8h9i0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add MFA columns to users table
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # Create backup codes table
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])
    op.create_index("ix_mfa_backup_codes_code_hash", "mfa_backup_codes", ["code_hash"])


def downgrade() -> None:
    op.drop_index("ix_mfa_backup_codes_code_hash", table_name="mfa_backup_codes")
    op.drop_index("ix_mfa_backup_codes_user_id", table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "mfa_enabled")
