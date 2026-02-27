import csv
import io
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_permission
from app.core.admin_roles import PERMISSION_ADMIN_READ
from app.core.database import get_db
from app.models.canonical_event_alignment import CanonicalEventAlignment
from app.models.exchange_quote_event import ExchangeQuoteEvent
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_csv_response(filename: str, header: list[str], rows: list[list[Any]]) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/alignments/export.csv")
async def export_alignments(
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    stmt = (
        select(CanonicalEventAlignment)
        .order_by(CanonicalEventAlignment.created_at.desc())
        .limit(limit)
    )
    results = (await db.execute(stmt)).scalars().all()

    header = [
        "canonical_event_key",
        "sportsbook_event_id",
        "kalshi_market_id",
        "start_time",
        "created_at",
    ]
    rows: list[list[Any]] = []
    for row in results:
        rows.append([
            row.canonical_event_key,
            row.sportsbook_event_id,
            row.kalshi_market_id,
            row.start_time.isoformat() if row.start_time else "",
            row.created_at.isoformat() if row.created_at else "",
        ])

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _build_csv_response(f"kalshi-alignments-{timestamp}.csv", header, rows)


@router.get("/quotes/export.csv")
async def export_quotes(
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    stmt = (
        select(ExchangeQuoteEvent)
        .where(ExchangeQuoteEvent.source == "KALSHI")
        .order_by(ExchangeQuoteEvent.timestamp.desc())
        .limit(limit)
    )
    results = (await db.execute(stmt)).scalars().all()

    header = [
        "canonical_event_key",
        "market_id",
        "outcome_name",
        "probability",
        "price",
        "timestamp",
        "created_at",
        "valid",
        "invalid_reason",
    ]
    rows: list[list[Any]] = []
    for row in results:
        valid = True
        invalid_reason = []
        if not row.market_id:
            valid = False
            invalid_reason.append("empty market_id")
        if row.probability is None or not (0 <= row.probability <= 1):
            valid = False
            invalid_reason.append(f"invalid probability: {row.probability}")
        if not row.timestamp:
            valid = False
            invalid_reason.append("null timestamp")
        if row.outcome_name != "YES":
            valid = False
            invalid_reason.append(f"outcome is not YES: {row.outcome_name}")

        rows.append([
            row.canonical_event_key,
            row.market_id,
            row.outcome_name,
            row.probability,
            row.price,
            row.timestamp.isoformat() if row.timestamp else "",
            row.created_at.isoformat() if row.created_at else "",
            valid,
            "; ".join(invalid_reason),
        ])

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _build_csv_response(f"kalshi-quotes-{timestamp}.csv", header, rows)


@router.get("/debug_view/export.csv")
async def export_debug_view(
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    align_stmt = select(CanonicalEventAlignment).order_by(CanonicalEventAlignment.created_at.desc()).limit(limit)
    alignments = (await db.execute(align_stmt)).scalars().all()

    if not alignments:
        return _build_csv_response("kalshi-debug-empty.csv", ["canonical_event_key"], [])

    sb_event_ids = [a.sportsbook_event_id for a in alignments]
    ce_keys = [a.canonical_event_key for a in alignments]

    struct_stmt = text('''
        SELECT DISTINCT ON (event_id) event_id, timestamp, threshold_value 
        FROM structural_events 
        WHERE event_id = ANY(:event_ids)
        ORDER BY event_id, timestamp DESC
    ''')
    structs = (await db.execute(struct_stmt, {"event_ids": sb_event_ids})).all()
    struct_map = {r.event_id: {"ts": r.timestamp, "threshold": r.threshold_value} for r in structs}

    quote_stmt = text('''
        SELECT DISTINCT ON (canonical_event_key) canonical_event_key, timestamp, probability 
        FROM exchange_quote_events 
        WHERE source = 'KALSHI' AND canonical_event_key = ANY(:ce_keys)
        ORDER BY canonical_event_key, timestamp DESC
    ''')
    quotes = (await db.execute(quote_stmt, {"ce_keys": ce_keys})).all()
    quote_map = {r.canonical_event_key: {"ts": r.timestamp, "prob": r.probability} for r in quotes}

    ll_stmt = text('''
        SELECT DISTINCT ON (canonical_event_key) canonical_event_key, created_at, lead_source, lag_seconds 
        FROM cross_market_lead_lag_events 
        WHERE canonical_event_key = ANY(:ce_keys)
        ORDER BY canonical_event_key, created_at DESC
    ''')
    lls = (await db.execute(ll_stmt, {"ce_keys": ce_keys})).all()
    ll_map = {r.canonical_event_key: {"created_at": r.created_at, "lead": r.lead_source, "lag": r.lag_seconds} for r in lls}

    div_stmt = text('''
        SELECT DISTINCT ON (canonical_event_key) canonical_event_key, created_at, divergence_type, resolved 
        FROM cross_market_divergence_events 
        WHERE canonical_event_key = ANY(:ce_keys)
        ORDER BY canonical_event_key, created_at DESC
    ''')
    divs = (await db.execute(div_stmt, {"ce_keys": ce_keys})).all()
    div_map = {r.canonical_event_key: {"created_at": r.created_at, "type": r.divergence_type, "resolved": r.resolved} for r in divs}

    header = [
        "canonical_event_key",
        "sportsbook_event_id",
        "last_structural_event_ts",
        "last_structural_threshold_value",
        "last_exchange_quote_ts",
        "last_exchange_probability",
        "last_lead_lag_created_at",
        "last_lead_source",
        "last_lag_seconds",
        "last_divergence_created_at",
        "last_divergence_type",
        "last_divergence_resolved",
    ]
    rows: list[list[Any]] = []
    def _iso(x: Any) -> str:
        return x.isoformat() if x else ""

    for row in alignments:
        cek = row.canonical_event_key
        sb_id = row.sportsbook_event_id
        st = struct_map.get(sb_id, {})
        qt = quote_map.get(cek, {})
        ll = ll_map.get(cek, {})
        div = div_map.get(cek, {})

        rows.append([
            cek,
            sb_id,
            _iso(st.get("ts")),
            st.get("threshold", ""),
            _iso(qt.get("ts")),
            qt.get("prob", ""),
            _iso(ll.get("created_at")),
            ll.get("lead", ""),
            ll.get("lag", ""),
            _iso(div.get("created_at")),
            div.get("type", ""),
            div.get("resolved", ""),
        ])

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _build_csv_response(f"kalshi-debug-view-{timestamp}.csv", header, rows)


@router.get("/idempotency_audit/export.csv")
async def export_idempotency_audit(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_permission(PERMISSION_ADMIN_READ)),
) -> StreamingResponse:
    header = ["check_name", "key_fields", "duplicate_count"]
    rows: list[list[Any]] = []

    eq_stmt = text('''
        SELECT source, market_id, outcome_name, timestamp, COUNT(*) as count 
        FROM exchange_quote_events 
        GROUP BY source, market_id, outcome_name, timestamp 
        HAVING COUNT(*) > 1
    ''')
    eq_dupes = (await db.execute(eq_stmt)).all()
    for row in eq_dupes:
        key_str = f"{row.source}|{row.market_id}|{row.outcome_name}|{row.timestamp}"
        rows.append(["ExchangeQuoteEvent", key_str, row.count])

    ll_stmt = text('''
        SELECT canonical_event_key, sportsbook_break_timestamp, exchange_break_timestamp, lead_source, lag_seconds, COUNT(*) as count 
        FROM cross_market_lead_lag_events 
        GROUP BY canonical_event_key, sportsbook_break_timestamp, exchange_break_timestamp, lead_source, lag_seconds 
        HAVING COUNT(*) > 1
    ''')
    ll_dupes = (await db.execute(ll_stmt)).all()
    for row in ll_dupes:
        key_str = f"{row.canonical_event_key}|{row.sportsbook_break_timestamp}|{row.exchange_break_timestamp}|{row.lead_source}|{row.lag_seconds}"
        rows.append(["CrossMarketLeadLagEvent", key_str, row.count])

    div_stmt = text('''
        SELECT idempotency_key, COUNT(*) as count 
        FROM cross_market_divergence_events 
        GROUP BY idempotency_key 
        HAVING COUNT(*) > 1
    ''')
    div_dupes = (await db.execute(div_stmt)).all()
    for row in div_dupes:
        rows.append(["CrossMarketDivergenceEvent", row.idempotency_key or "NULL", row.count])

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _build_csv_response(f"kalshi-idempotency-audit-{timestamp}.csv", header, rows)
