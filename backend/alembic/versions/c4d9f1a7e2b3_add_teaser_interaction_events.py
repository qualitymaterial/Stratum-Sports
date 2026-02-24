"""add_teaser_interaction_events

Revision ID: c4d9f1a7e2b3
Revises: b1c4f9e2d8a7
Create Date: 2026-02-24 14:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d9f1a7e2b3"
down_revision: Union[str, None] = "b1c4f9e2d8a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teaser_interaction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("sport_key", sa.String(length=64), nullable=True),
        sa.Column("user_tier", sa.String(length=16), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teaser_interaction_events_user_id", "teaser_interaction_events", ["user_id"], unique=False)
    op.create_index(
        "ix_teaser_interaction_events_event_name",
        "teaser_interaction_events",
        ["event_name"],
        unique=False,
    )
    op.create_index(
        "ix_teaser_interaction_events_sport_key",
        "teaser_interaction_events",
        ["sport_key"],
        unique=False,
    )
    op.create_index(
        "ix_teaser_interaction_events_created_at",
        "teaser_interaction_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_teaser_interaction_events_created_event_sport",
        "teaser_interaction_events",
        [sa.text("created_at DESC"), "event_name", "sport_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_teaser_interaction_events_created_event_sport", table_name="teaser_interaction_events")
    op.drop_index("ix_teaser_interaction_events_created_at", table_name="teaser_interaction_events")
    op.drop_index("ix_teaser_interaction_events_sport_key", table_name="teaser_interaction_events")
    op.drop_index("ix_teaser_interaction_events_event_name", table_name="teaser_interaction_events")
    op.drop_index("ix_teaser_interaction_events_user_id", table_name="teaser_interaction_events")
    op.drop_table("teaser_interaction_events")
