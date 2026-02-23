import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.closing_consensus import ClosingConsensus
from app.models.clv_record import ClvRecord
from app.models.game import Game
from app.models.signal import Signal
from app.services.closing import compute_and_persist_closing_consensus

logger = logging.getLogger(__name__)


def american_to_implied_prob(price: float | int | None) -> float | None:
    if price is None:
        return None
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None

    if value == 0:
        return None
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_entry(signal: Signal) -> tuple[str | None, float | None, float | None]:
    metadata = signal.metadata_json or {}
    raw_outcome = metadata.get("outcome_name")
    outcome_name = raw_outcome.strip() if isinstance(raw_outcome, str) else None
    if not outcome_name:
        return None, None, None

    entry_line: float | None = None
    entry_price: float | None = None

    if signal.signal_type == "DISLOCATION":
        entry_line = _coerce_float(metadata.get("book_line"))
        entry_price = _coerce_float(metadata.get("book_price"))
    elif signal.signal_type == "STEAM":
        entry_line = _coerce_float(metadata.get("entry_line"))
        if entry_line is None:
            entry_line = _coerce_float(metadata.get("end_line"))
    elif signal.signal_type in {"MOVE", "KEY_CROSS", "MULTIBOOK_SYNC"}:
        if signal.market == "h2h":
            base_price = signal.to_price if signal.to_price is not None else signal.from_price
            entry_price = float(base_price) if base_price is not None else None
        else:
            entry_line = float(signal.to_value)
    else:
        if signal.market == "h2h":
            base_price = signal.to_price if signal.to_price is not None else signal.from_price
            entry_price = float(base_price) if base_price is not None else None
        else:
            entry_line = float(signal.to_value)

    return outcome_name, entry_line, entry_price


async def compute_and_persist_clv(db: AsyncSession, days_lookback: int | None = None) -> int:
    settings = get_settings()
    if not settings.clv_enabled:
        return 0

    lookback_days = days_lookback if days_lookback is not None else settings.clv_lookback_days
    now = datetime.now(UTC)
    ready_cutoff = now - timedelta(minutes=settings.clv_minutes_after_commence)
    lookback_start = ready_cutoff - timedelta(days=lookback_days)

    games_stmt = (
        select(Game.event_id, Game.commence_time)
        .where(
            Game.commence_time >= lookback_start,
            Game.commence_time <= ready_cutoff,
        )
        .order_by(Game.commence_time.asc())
    )
    games = (await db.execute(games_stmt)).all()
    if not games:
        return 0

    event_ids = sorted({row.event_id for row in games})
    commence_by_event = {row.event_id: row.commence_time for row in games}

    closing_upserts = await compute_and_persist_closing_consensus(db, event_ids)

    closes_stmt = select(ClosingConsensus).where(ClosingConsensus.event_id.in_(event_ids))
    closes = (await db.execute(closes_stmt)).scalars().all()
    close_map = {(row.event_id, row.market, row.outcome_name): row for row in closes}
    if not close_map:
        return 0

    signals_stmt = (
        select(Signal)
        .outerjoin(ClvRecord, ClvRecord.signal_id == Signal.id)
        .where(
            Signal.event_id.in_(event_ids),
            Signal.created_at <= ready_cutoff,
            ClvRecord.signal_id.is_(None),
        )
        .order_by(Signal.created_at.asc())
    )
    signals = (await db.execute(signals_stmt)).scalars().all()
    if not signals:
        return 0

    inserted = 0
    skipped_missing_outcome = 0
    skipped_missing_close = 0

    for signal in signals:
        event_commence = commence_by_event.get(signal.event_id)
        if event_commence is None or signal.created_at > event_commence:
            continue

        outcome_name, entry_line, entry_price = _extract_entry(signal)
        if not outcome_name:
            skipped_missing_outcome += 1
            continue

        close = close_map.get((signal.event_id, signal.market, outcome_name))
        if close is None:
            skipped_missing_close += 1
            continue

        close_line = float(close.close_line) if close.close_line is not None else None
        close_price = float(close.close_price) if close.close_price is not None else None

        clv_line = None
        if close_line is not None and entry_line is not None:
            clv_line = close_line - entry_line

        clv_prob = None
        close_prob = american_to_implied_prob(close_price)
        entry_prob = american_to_implied_prob(entry_price)
        if close_prob is not None and entry_prob is not None:
            clv_prob = close_prob - entry_prob

        if clv_line is None and clv_prob is None:
            skipped_missing_close += 1
            continue

        db.add(
            ClvRecord(
                signal_id=signal.id,
                event_id=signal.event_id,
                signal_type=signal.signal_type,
                market=signal.market,
                outcome_name=outcome_name,
                entry_line=entry_line,
                entry_price=entry_price,
                close_line=close_line,
                close_price=close_price,
                clv_line=clv_line,
                clv_prob=clv_prob,
                computed_at=now,
            )
        )
        inserted += 1

    if inserted > 0:
        await db.commit()

    logger.info(
        "CLV computation completed",
        extra={
            "clv_events_scanned": len(event_ids),
            "closing_upserts": closing_upserts,
            "clv_records_inserted": inserted,
            "clv_skipped_missing_outcome": skipped_missing_outcome,
            "clv_skipped_missing_close": skipped_missing_close,
        },
    )
    return inserted


async def cleanup_old_clv_records(db: AsyncSession, retention_days: int | None = None) -> int:
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.clv_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = delete(ClvRecord).where(ClvRecord.computed_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
