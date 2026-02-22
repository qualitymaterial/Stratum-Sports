import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.closing_consensus import ClosingConsensus
from app.models.game import Game
from app.models.market_consensus_snapshot import MarketConsensusSnapshot

logger = logging.getLogger(__name__)


async def compute_and_persist_closing_consensus(db: AsyncSession, event_ids: list[str]) -> int:
    settings = get_settings()
    if not settings.clv_enabled or not event_ids:
        return 0

    now = datetime.now(UTC)
    commence_cutoff = now - timedelta(minutes=settings.clv_minutes_after_commence)
    eligible_games_subquery = (
        select(
            Game.event_id.label("event_id"),
            Game.commence_time.label("commence_time"),
        )
        .where(
            Game.event_id.in_(event_ids),
            Game.commence_time <= commence_cutoff,
        )
        .subquery()
    )

    latest_subquery = (
        select(
            MarketConsensusSnapshot.event_id.label("event_id"),
            MarketConsensusSnapshot.market.label("market"),
            MarketConsensusSnapshot.outcome_name.label("outcome_name"),
            func.max(MarketConsensusSnapshot.fetched_at).label("close_fetched_at"),
        )
        .join(
            eligible_games_subquery,
            MarketConsensusSnapshot.event_id == eligible_games_subquery.c.event_id,
        )
        .where(MarketConsensusSnapshot.fetched_at <= eligible_games_subquery.c.commence_time)
        .group_by(
            MarketConsensusSnapshot.event_id,
            MarketConsensusSnapshot.market,
            MarketConsensusSnapshot.outcome_name,
        )
        .subquery()
    )

    rows_stmt = (
        select(
            MarketConsensusSnapshot.event_id,
            MarketConsensusSnapshot.market,
            MarketConsensusSnapshot.outcome_name,
            MarketConsensusSnapshot.consensus_line,
            MarketConsensusSnapshot.consensus_price,
            MarketConsensusSnapshot.fetched_at,
        )
        .join(
            latest_subquery,
            and_(
                MarketConsensusSnapshot.event_id == latest_subquery.c.event_id,
                MarketConsensusSnapshot.market == latest_subquery.c.market,
                MarketConsensusSnapshot.outcome_name == latest_subquery.c.outcome_name,
                MarketConsensusSnapshot.fetched_at == latest_subquery.c.close_fetched_at,
            ),
        )
        .order_by(
            MarketConsensusSnapshot.event_id.asc(),
            MarketConsensusSnapshot.market.asc(),
            MarketConsensusSnapshot.outcome_name.asc(),
        )
    )
    rows = (await db.execute(rows_stmt)).all()
    if not rows:
        return 0

    upserts = 0
    for row in rows:
        upsert_stmt = pg_insert(ClosingConsensus).values(
            event_id=row.event_id,
            market=row.market,
            outcome_name=row.outcome_name,
            close_line=float(row.consensus_line) if row.consensus_line is not None else None,
            close_price=float(row.consensus_price) if row.consensus_price is not None else None,
            close_fetched_at=row.fetched_at,
            computed_at=now,
        )
        upsert_stmt = upsert_stmt.on_conflict_do_update(
            index_elements=["event_id", "market", "outcome_name"],
            set_={
                "close_line": upsert_stmt.excluded.close_line,
                "close_price": upsert_stmt.excluded.close_price,
                "close_fetched_at": upsert_stmt.excluded.close_fetched_at,
                "computed_at": upsert_stmt.excluded.computed_at,
            },
        )
        await db.execute(upsert_stmt)
        upserts += 1

    await db.commit()
    return upserts


async def cleanup_old_closing_consensus(
    db: AsyncSession,
    retention_days: int | None = None,
) -> int:
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.clv_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = delete(ClosingConsensus).where(ClosingConsensus.computed_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
