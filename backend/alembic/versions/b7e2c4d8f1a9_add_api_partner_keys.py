"""add api partner keys

Revision ID: b7e2c4d8f1a9
Revises: aa7d5c4e9b12
Create Date: 2026-02-25 20:40:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7e2c4d8f1a9"
down_revision: Union[str, None] = "aa7d5c4e9b12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_partner_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_partner_keys_user_id", "api_partner_keys", ["user_id"], unique=False)
    op.create_index(
        "ix_api_partner_keys_created_by_user_id",
        "api_partner_keys",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index("ix_api_partner_keys_key_prefix", "api_partner_keys", ["key_prefix"], unique=False)
    op.create_index("ix_api_partner_keys_key_hash", "api_partner_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_partner_keys_is_active", "api_partner_keys", ["is_active"], unique=False)
    op.create_index("ix_api_partner_keys_expires_at", "api_partner_keys", ["expires_at"], unique=False)
    op.create_index("ix_api_partner_keys_revoked_at", "api_partner_keys", ["revoked_at"], unique=False)
    op.execute("CREATE INDEX ix_api_partner_keys_user_active ON api_partner_keys (user_id, is_active)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_partner_keys_user_active")
    op.drop_index("ix_api_partner_keys_revoked_at", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_expires_at", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_is_active", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_key_hash", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_key_prefix", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_created_by_user_id", table_name="api_partner_keys")
    op.drop_index("ix_api_partner_keys_user_id", table_name="api_partner_keys")
    op.drop_table("api_partner_keys")
