"""add api partner entitlements

Revision ID: c3f6e2a1b9d4
Revises: b7e2c4d8f1a9
Create Date: 2026-02-26 00:15:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3f6e2a1b9d4"
down_revision: Union[str, None] = "b7e2c4d8f1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_partner_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=True),
        sa.Column(
            "api_access_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("soft_limit_monthly", sa.Integer(), nullable=True),
        sa.Column(
            "overage_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("overage_price_cents", sa.Integer(), nullable=True),
        sa.Column(
            "overage_unit_quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1000"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_api_partner_entitlements_user_id"),
    )
    op.create_index(
        "ix_api_partner_entitlements_user_id",
        "api_partner_entitlements",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_api_partner_entitlements_plan_code",
        "api_partner_entitlements",
        ["plan_code"],
        unique=False,
    )
    op.create_index(
        "ix_api_partner_entitlements_api_access_enabled",
        "api_partner_entitlements",
        ["api_access_enabled"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX ix_api_partner_entitlements_access_plan ON api_partner_entitlements "
        "(api_access_enabled, plan_code)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_partner_entitlements_access_plan")
    op.drop_index("ix_api_partner_entitlements_api_access_enabled", table_name="api_partner_entitlements")
    op.drop_index("ix_api_partner_entitlements_plan_code", table_name="api_partner_entitlements")
    op.drop_index("ix_api_partner_entitlements_user_id", table_name="api_partner_entitlements")
    op.drop_table("api_partner_entitlements")
