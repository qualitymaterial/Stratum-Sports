# Kalshi Integration Verification & Debugging

This guide outlines how to verify, monitor, and debug the Kalshi exchange integration within Stratum Sports.

## 1. Overview
The Kalshi integration allows Stratum to fetch real-time and structural outcome probabilities from kalshi.com and align them with canonical sportsbook events. The ingest pipeline operates on a continuous polling loop, matching configured events by their unique Kalshi IDs and validating incoming pricing.

## 2. Admin Verification Export Endpoints
We expose four admin-only endpoints to inspect Kalshi integration state directly via CSV downloads. All endpoints are mounted under `/admin/kalshi/` and require the `PERMISSION_ADMIN_READ` auth scope.

### `GET /admin/kalshi/alignments/export.csv`
Returns all `CanonicalEventAlignment` rows containing Kalshi mapping data. Use this to verify that upcoming sportsbook events have legitimately mapped `kalshi_market_id` fields.
**Fields:**
- `canonical_event_key`
- `sportsbook_event_id`
- `kalshi_market_id`
- `start_time`
- `created_at`

### `GET /admin/kalshi/quotes/export.csv`
Exports raw ingest events (`ExchangeQuoteEvent`) gathered specifically from Kalshi. This also performs on-the-fly validity checking (e.g. valid timestamps, bounded probabilities 0.0 - 1.0, and target outcome sets). 
**Fields include validation flags:**
- `valid` (Boolean)
- `invalid_reason` (Text describing validation failure context if `valid` is False)

### `GET /admin/kalshi/debug_view/export.csv`
A joined structural view across several tables to help diagnose the pipeline end-to-end. For a given alignment, this view pulls the latest `StructuralEvent`, latest `ExchangeQuoteEvent` (Kalshi), latest `CrossMarketLeadLagEvent`, and latest `CrossMarketDivergenceEvent`. This allows you to immediately see whether Kalshi pricing successfully precipitated lead-lag or divergence flags for a given event.

### `GET /admin/kalshi/idempotency_audit/export.csv`
Performs an aggregation check across all exchange-dependent tables to discover idempotency violations (duplicate rows). If no duplicates exist, this export will yield 0 rows. Identifies duplicated `ExchangeQuoteEvent`, `CrossMarketLeadLagEvent`, or `CrossMarketDivergenceEvent` rows.

## 3. Poller Observability
The core data fetcher routine operates out of `app/tasks/poller.py`.
The return dictionary of every polling cycle now tracks these Kalshi-specific telemetry keys:
- `kalshi_markets_polled`: Number of populated alignment markets requested
- `kalshi_quotes_inserted`: New quoting events persisted to DB
- `kalshi_errors`: Any unhandled exceptions or network errors (pipeline fails-open)
- `kalshi_skipped_no_alignment`: Canonical events missing DB alignment logic entirely
- `kalshi_skipped_no_market_id`: Aligned events that lack the `kalshi_market_id` explicitly

**Log Signatures:**
During ingestion, the poller emits a single, machine-readable summary line at the standard `{logger.info}` tier:
`KALSHI_INGEST_SUMMARY polled=X inserted=Y errors=Z skipped_no_alignment=N skipped_no_market=M`

## 4. Debugging Common Issues
* **Kalshi prices are not updating:** Check `kalshi_errors` in telemetry. If the Kalshi upstream is rate-limiting or throwing 5xx, the poller will fail-open and skip updates. You will see an incremented `kalshi_errors` counter.
* **Events show 0 quotes continuously:** Use the `/admin/kalshi/alignments` export. Ensure that `CanonicalEventAlignment` config exists with valid non-null `kalshi_market_id` values. The counter `kalshi_skipped_no_market_id` will flag this.
* **Duplication of Lead-Lag entries:** Run the `/admin/kalshi/idempotency_audit/export.csv`. 

For further queries or adjustments to polling capacities, adjust `MAX_KALSHI_MARKETS_PER_CYCLE` in system env configurations.
