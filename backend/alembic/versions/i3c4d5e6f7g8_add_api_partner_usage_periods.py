"""add api_partner_usage_periods table

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "i3c4d5e6f7g8"
down_revision = "h2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_partner_usage_periods",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_id", UUID(as_uuid=True), sa.ForeignKey("api_partner_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("included_limit", sa.Integer, nullable=True),
        sa.Column("overage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stripe_meter_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "key_id", "period_start", name="uq_usage_period_user_key_start"),
    )
    op.create_index("ix_api_partner_usage_periods_user_id", "api_partner_usage_periods", ["user_id"])
    op.create_index("ix_api_partner_usage_periods_key_id", "api_partner_usage_periods", ["key_id"])
    op.create_index("ix_api_partner_usage_periods_period_start", "api_partner_usage_periods", ["period_start"])
    op.create_index(
        "ix_api_partner_usage_periods_user_period",
        "api_partner_usage_periods",
        ["user_id", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_partner_usage_periods_user_period", table_name="api_partner_usage_periods")
    op.drop_index("ix_api_partner_usage_periods_period_start", table_name="api_partner_usage_periods")
    op.drop_index("ix_api_partner_usage_periods_key_id", table_name="api_partner_usage_periods")
    op.drop_index("ix_api_partner_usage_periods_user_id", table_name="api_partner_usage_periods")
    op.drop_table("api_partner_usage_periods")
