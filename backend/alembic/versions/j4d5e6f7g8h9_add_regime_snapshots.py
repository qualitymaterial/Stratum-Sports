"""add regime_snapshots table

Revision ID: j4d5e6f7g8h9
Revises: i3c4d5e6f7g8
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "j4d5e6f7g8h9"
down_revision = "i3c4d5e6f7g8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regime_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("regime_label", sa.String(16), nullable=False),
        sa.Column("regime_probability", sa.Float, nullable=False),
        sa.Column("transition_risk", sa.Float, nullable=False),
        sa.Column("stability_score", sa.Float, nullable=False),
        sa.Column("model_version", sa.String(16), nullable=False),
        sa.Column("snapshots_used", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_regime_snapshots_event_id", "regime_snapshots", ["event_id"])
    op.create_index("ix_regime_snapshots_market", "regime_snapshots", ["market"])
    op.create_index("ix_regime_snapshots_created_at", "regime_snapshots", ["created_at"])
    op.create_index(
        "ix_regime_snapshots_event_market_created_desc",
        "regime_snapshots",
        ["event_id", "market", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_regime_snapshots_event_market_created_desc", table_name="regime_snapshots")
    op.drop_index("ix_regime_snapshots_created_at", table_name="regime_snapshots")
    op.drop_index("ix_regime_snapshots_market", table_name="regime_snapshots")
    op.drop_index("ix_regime_snapshots_event_id", table_name="regime_snapshots")
    op.drop_table("regime_snapshots")
