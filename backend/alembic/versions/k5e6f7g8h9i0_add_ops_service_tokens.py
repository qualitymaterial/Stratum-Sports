"""add ops_service_tokens table

Revision ID: k5e6f7g8h9i0
Revises: j4d5e6f7g8h9
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k5e6f7g8h9i0"
down_revision = "j4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_service_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ops_service_tokens_key_prefix",
        "ops_service_tokens",
        ["key_prefix"],
    )
    op.create_index(
        "ix_ops_service_tokens_key_hash",
        "ops_service_tokens",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_ops_service_tokens_is_active",
        "ops_service_tokens",
        ["is_active"],
    )
    op.create_index(
        "ix_ops_service_tokens_created_by_user_id",
        "ops_service_tokens",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_ops_service_tokens_expires_at",
        "ops_service_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_ops_service_tokens_revoked_at",
        "ops_service_tokens",
        ["revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_service_tokens_revoked_at", table_name="ops_service_tokens")
    op.drop_index("ix_ops_service_tokens_expires_at", table_name="ops_service_tokens")
    op.drop_index("ix_ops_service_tokens_created_by_user_id", table_name="ops_service_tokens")
    op.drop_index("ix_ops_service_tokens_is_active", table_name="ops_service_tokens")
    op.drop_index("ix_ops_service_tokens_key_hash", table_name="ops_service_tokens")
    op.drop_index("ix_ops_service_tokens_key_prefix", table_name="ops_service_tokens")
    op.drop_table("ops_service_tokens")
