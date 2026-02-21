"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-21 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tier", "users", ["tier"], unique=False)
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=False)
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"], unique=False)
    op.create_index("ix_subscriptions_stripe_customer_id", "subscriptions", ["stripe_customer_id"], unique=False)
    op.create_unique_constraint("uq_subscriptions_stripe_subscription_id", "subscriptions", ["stripe_subscription_id"])

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("sport_key", sa.String(length=64), nullable=False),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team", sa.String(length=120), nullable=False),
        sa.Column("away_team", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_games_event_id", "games", ["event_id"])
    op.create_index("ix_games_event_id", "games", ["event_id"], unique=True)
    op.create_index("ix_games_sport_key", "games", ["sport_key"], unique=False)
    op.create_index("ix_games_commence_time", "games", ["commence_time"], unique=False)

    op.create_table(
        "odds_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("sport_key", sa.String(length=64), nullable=False),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team", sa.String(length=120), nullable=False),
        sa.Column("away_team", sa.String(length=120), nullable=False),
        sa.Column("sportsbook_key", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("outcome_name", sa.String(length=120), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_odds_snapshots_event_id", "odds_snapshots", ["event_id"], unique=False)
    op.create_index("ix_odds_snapshots_sport_key", "odds_snapshots", ["sport_key"], unique=False)
    op.create_index("ix_odds_snapshots_sportsbook_key", "odds_snapshots", ["sportsbook_key"], unique=False)
    op.create_index("ix_odds_snapshots_market", "odds_snapshots", ["market"], unique=False)
    op.create_index("ix_odds_snapshots_fetched_at", "odds_snapshots", ["fetched_at"], unique=False)
    op.create_index(
        "ix_odds_snapshots_event_market_outcome_book_fetched",
        "odds_snapshots",
        ["event_id", "market", "outcome_name", "sportsbook_key", "fetched_at"],
        unique=False,
    )

    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("from_value", sa.Float(), nullable=False),
        sa.Column("to_value", sa.Float(), nullable=False),
        sa.Column("from_price", sa.Integer(), nullable=True),
        sa.Column("to_price", sa.Integer(), nullable=True),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("books_affected", sa.Integer(), nullable=False),
        sa.Column("velocity_minutes", sa.Float(), nullable=False),
        sa.Column("strength_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_signals_event_id", "signals", ["event_id"], unique=False)
    op.create_index("ix_signals_market", "signals", ["market"], unique=False)
    op.create_index("ix_signals_signal_type", "signals", ["signal_type"], unique=False)
    op.create_index("ix_signals_created_at", "signals", ["created_at"], unique=False)

    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "event_id", name="uq_watchlist_user_event"),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"], unique=False)
    op.create_index("ix_watchlists_event_id", "watchlists", ["event_id"], unique=False)

    op.create_table(
        "discord_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("webhook_url", sa.String(length=1000), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("alert_spreads", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("alert_totals", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("alert_multibook", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_strength", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("discord_connections")
    op.drop_index("ix_watchlists_event_id", table_name="watchlists")
    op.drop_index("ix_watchlists_user_id", table_name="watchlists")
    op.drop_table("watchlists")

    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_index("ix_signals_signal_type", table_name="signals")
    op.drop_index("ix_signals_market", table_name="signals")
    op.drop_index("ix_signals_event_id", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_odds_snapshots_event_market_outcome_book_fetched", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_fetched_at", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_market", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_sportsbook_key", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_sport_key", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_event_id", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")

    op.drop_index("ix_games_commence_time", table_name="games")
    op.drop_index("ix_games_sport_key", table_name="games")
    op.drop_index("ix_games_event_id", table_name="games")
    op.drop_table("games")

    op.drop_constraint("uq_subscriptions_stripe_subscription_id", "subscriptions", type_="unique")
    op.drop_index("ix_subscriptions_stripe_customer_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_index("ix_users_tier", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
