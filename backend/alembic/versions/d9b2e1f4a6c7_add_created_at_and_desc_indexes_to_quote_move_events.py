"""add created_at and desc indexes to quote_move_events

Revision ID: d9b2e1f4a6c7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9b2e1f4a6c7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_move_events",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quote_move_events_event_market_outcome_ts_desc "
        "ON quote_move_events (event_id, market_key, outcome_name, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quote_move_events_venue_timestamp_desc "
        "ON quote_move_events (venue, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_quote_move_events_venue_timestamp_desc")
    op.execute("DROP INDEX IF EXISTS ix_quote_move_events_event_market_outcome_ts_desc")
    op.drop_column("quote_move_events", "created_at")
