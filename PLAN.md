# Stratum Sports — Full-Access Odds API Integration Plan (Architecture-Fit, Low-Bloat)

## Summary
Stratum Sports already has a strong production MVP core: async ingestion, persisted time-series snapshots, explainable signaling, Pro-tier gated alerts, and reliable Dockerized ops.  
The highest-leverage path is to **extend the existing cycle** (not rewrite it) with 3 immediate additions:
1. Persisted consensus/dispersion snapshots
2. Book dislocation signals
3. Steam/movement v2 signals

Then add:
4. Watchlist-scoped live shock alerts
5. Historical close + CLV analytics

This sequence maximizes monetizable analytics value while controlling API cost and preserving current reliability patterns.

---

## Deliverable A — What Stratum Sports Already Does (Best Features)

## Current Modules and Responsibilities (Read-Only Orientation)
| Module | Responsibility | Key locations |
|---|---|---|
| Runner / scheduler | Polling loop, adaptive cadence, lock, cleanup | `backend/app/tasks/poller.py` (`main`, `run_polling_cycle`, `determine_poll_interval`) |
| Odds fetch client | External API calls + credit header parsing | `backend/app/services/odds_api.py` (`OddsApiClient.fetch_nba_odds`) |
| Ingestion engine | Normalize, dedupe, persist snapshots, publish realtime updates | `backend/app/services/ingestion.py` (`ingest_odds_cycle`) |
| Signal engine | Movement detection, key-cross, multibook sync, strength scoring | `backend/app/services/signals.py` (`detect_market_movements`, `compute_strength_score`) |
| Alert router | Pro watchlist + Discord preference filtering + send | `backend/app/services/discord_alerts.py` (`dispatch_discord_alerts_for_signals`) |
| Data shaping for UI/API | Consensus views, chart series, game detail assembly | `backend/app/services/market_data.py` (`build_dashboard_cards`, `build_game_detail`) |
| Context framework | Stub analytics for injuries/props/pace | `backend/app/services/context_score/*` |
| Persistence | SQLAlchemy models + Alembic migrations | `backend/app/models/*`, `backend/alembic/versions/0001_initial.py` |
| API surface | Auth, dashboard, games, watchlist, billing, discord, websocket | `backend/app/api/routes/*`, `backend/app/api/router.py` |
| Security / ops | JWT auth, OAuth state hardening, rate limiting, structured logs | `backend/app/core/security.py`, `backend/app/core/rate_limit.py`, `backend/app/core/logging.py` |
| Frontend app | Dashboard, game detail, watchlist, Discord settings, websocket client | `frontend/app/app/*`, `frontend/lib/useOddsSocket.ts` |
| Backtesting / research | Not implemented | N/A |

## Current Cycle Flow (Fetch → Transform → Score → Alert)
1. Worker loop starts in `backend/app/tasks/poller.py` and acquires Redis cycle lock (`redis_cycle_lock`).
2. Poller calls `ingest_odds_cycle` in `backend/app/services/ingestion.py`.
3. Ingestion calls `OddsApiClient.fetch_nba_odds` in `backend/app/services/odds_api.py`.
4. Payload is normalized into `OddsSnapshot` rows and `Game` upserts.
5. Redis dedupe key prevents duplicate snapshot inserts: `odds:last:{event}:{book}:{market}:{outcome}`.
6. Each inserted snapshot emits Pub/Sub `odds_updates` for realtime stream.
7. Poller passes updated `event_ids` to `detect_market_movements` in `backend/app/services/signals.py`.
8. Signal engine computes `MOVE`, `KEY_CROSS`, `MULTIBOOK_SYNC`, commits `Signal` rows.
9. Poller calls `dispatch_discord_alerts_for_signals` to send Pro webhook alerts for watchlisted events.
10. Periodic retention cleanup runs (`cleanup_old_snapshots`, `cleanup_old_signals`).
11. Adaptive interval uses `x-requests-*` headers and low-credit budget guardrails.

## Current Alert Types, Scoring, Thresholds, Context
- Spread triggers: abs move `>= 0.5` or key-number cross (`NBA_KEY_NUMBERS`).
- Total triggers: abs move `>= 1.0`.
- Multibook trigger: `>= 3` books same direction in 5m window.
- Strength score: magnitude component + speed component + books component, clamped 1..100.
- Discord thresholds: per-user `min_strength`, per-type toggles (`alert_spreads`, `alert_totals`, `alert_multibook`).
- Context score (scaffold): injuries/props/pace proxies in `backend/app/services/context_score/*`.

## Current Persistence and Between-Cycle State
- Postgres:
  - `games`
  - `odds_snapshots`
  - `signals`
  - `watchlists`
  - `discord_connections`
  - `users`, `subscriptions`
- Redis:
  - cycle lock: `poller:odds-ingest-lock`
  - odds dedupe: `odds:last:*`
  - signal dedupe: `signal:*`
  - realtime pubsub channel: `odds_updates`
  - API rate-limit buckets: `ratelimit:{ip}:{minute}`
  - OAuth replay key: `oauth:discord:state:{nonce}`

## Current Configuration Surface
- Central settings object: `backend/app/core/config.py` (`Settings`)
- Env templates: `.env.example`, `.env.production.example`
- Core odds controls:
  - `ODDS_API_*`
  - poll intervals and daily budget
  - book/region/market filters
- Tier gating controls:
  - `FREE_DELAY_MINUTES`
  - `FREE_WATCHLIST_LIMIT`

## Top Features and Why They Are Strong
1. Adaptive API budget control  
Location: `backend/app/tasks/poller.py` + `backend/app/services/odds_api.py`  
Why strong: Uses real provider cost headers and dynamically throttles to preserve credits.
2. Clean normalized time-series persistence  
Location: `backend/app/services/ingestion.py`, `backend/app/models/odds_snapshot.py`  
Why strong: Event/book/market/outcome granularity supports signaling, charting, and exports.
3. Explainable signal engine  
Location: `backend/app/services/signals.py`  
Why strong: Deterministic thresholds + explicit metadata components for trust and auditability.
4. Hard backend tier gating  
Location: `backend/app/core/tier.py`, `backend/app/api/deps.py`, `backend/app/services/signals.py`  
Why strong: Access control enforced server-side, not only UI masking.
5. Integrated realtime + alert automation  
Location: `backend/app/services/ingestion.py`, `backend/app/api/routes/ws.py`, `backend/app/services/discord_alerts.py`  
Why strong: Supports both dashboard live updates and operational Discord distribution from same cycle.

---

## Deliverable B — Capabilities Matrix

| Capability | Maturity (0-3) | Robustness Notes | Gaps |
|---|---:|---|---|
| Data ingest (pregame odds) | 2 | Async poller, dedupe, upsert, retention cleanup | Single endpoint path only; no modular endpoint selection |
| Normalization | 2 | Stable schema for h2h/spreads/totals | No generalized normalizer for props/historical/live variants |
| Scoring/signals | 2 | Clear rules + metadata + unit tests | Missing dislocation/steam-v2/live-shock/CLV signals |
| Alert routing | 2 | Pro-only, per-user prefs, min-strength, Discord delivery | No batching/digest, no retry queue, no delivery metrics table |
| Persistence | 2 | Indexed snapshots/signals and normalized games | No consensus snapshot table, no props table, no closing-line table |
| Scheduling/job coordination | 2 | Redis lock + adaptive intervals + cleanup cadence | Single-loop architecture for all tasks; no sub-job prioritization |
| Monitoring/ops | 1 | Health endpoints, structured logs, optional Sentry | No metrics endpoint, no SLO dashboard, no cycle KPI persistence |
| Docs/runbooks | 2 | README + deploy runbook + user guide | Missing feature-level engineering spec for Odds API full-access roadmap |
| Testing | 1 | Signal + auth + watchlist + billing + poll interval tests | No parser fuzz tests, no end-to-end cycle tests, no alert delivery tests |
| Backtesting/research | 0 | None | No evaluation loop for signal effectiveness |

## Top 5 Strengths
1. Strong ingestion-to-alert operational loop already in production shape.
2. Efficient DB query patterns in signaling and dashboard data assembly.
3. Cost-aware polling controls tied to real provider usage headers.
4. Tier-gated architecture with backend enforcement.
5. Clear modular separation (fetch/ingest/signal/alert/api).

## Top 5 Gaps
1. No persistent consensus/dislocation layer despite raw data availability.
2. No live-watchlist strategy (high value) with bounded request budget.
3. No historical close/CLV analytics to quantify signal quality.
4. No props ingestion foundation for phase-2 monetizable analytics.
5. Observability lacks cycle KPIs/metrics persistence for operator insight.

---

## Deliverable C — Integration Opportunities Ranked

## Ranking Rubric
- Monetizable analytics value
- Feasibility (<1–2 weeks)
- Infra delta (higher score = lower extra infra)
- Explainability
- Cross-sport reusability

| Rank | Opportunity | Value | Feasibility | Infra Delta | Explainability | Reuse | Total /25 | Tier |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Book dislocation scanner + dislocation score | 5 | 5 | 5 | 5 | 4 | 24 | Tier 1 |
| 2 | Steam detection v2 (movement velocity + book sync tightening) | 5 | 5 | 5 | 4 | 4 | 23 | Tier 1 |
| 3 | Persisted consensus/dispersion snapshots | 4 | 5 | 4 | 5 | 4 | 22 | Tier 1 |
| 4 | Watchlist-scoped live shock alerts | 5 | 3 | 3 | 4 | 4 | 19 | Tier 2 |
| 5 | Historical close ingestion + CLV tracker | 4 | 3 | 3 | 5 | 4 | 19 | Tier 2 |
| 6 | Player props ingestion foundation (limited markets) | 4 | 3 | 2 | 4 | 5 | 18 | Tier 2 |
| 7 | Player props mispricing radar (model-driven) | 5 | 2 | 2 | 3 | 5 | 17 | Tier 3 |

## Candidate Scoping (Value, Effort, Data, Cost, Risk, Fit)

1. Book dislocation scanner + dislocation score  
Value: Identifies outlier books vs market consensus for immediate actionable market intelligence.  
Effort: 4-6 days.  
Data needed: Existing pregame odds feed (`h2h`, `spreads`, `totals`) with bookmaker keys.  
Storage: Reuse `signals` with `signal_type="DISLOCATION"` and metadata fields for book/consensus/edge. Optional `market_consensus_snapshots` table for auditability.  
Computations: Consensus line/price, deviation z-score, edge score, trigger thresholds by market.  
API cost impact: Near-zero incremental if computed from existing snapshots.  
Dependencies/risks: Book naming consistency and sparse book coverage on low-liquidity games.  
Cycle fit: Insert after `ingest_odds_cycle`, before or inside `detect_market_movements`.

2. Steam detection v2  
Value: Better movement intelligence by measuring coordinated, fast multi-book shifts.  
Effort: 3-5 days.  
Data needed: Existing snapshots only.  
Storage: Reuse `signals` with `signal_type="STEAM"` and expanded metadata.  
Computations: Time-window sync, direction agreement, min-book-count, magnitude floor, acceleration.  
API cost impact: None incremental.  
Dependencies/risks: False positives during market open/illiquid periods.  
Cycle fit: Extend `backend/app/services/signals.py` detection sequence.

3. Persisted consensus/dispersion snapshots  
Value: Enables stable analytics APIs and supports dislocation/steam explainability.  
Effort: 4-6 days.  
Data needed: Existing snapshots.  
Storage: New `market_consensus_snapshots` table.  
Computations: Weighted/unweighted consensus, median, stddev, books_count.  
API cost impact: None incremental.  
Dependencies/risks: Snapshot growth; requires retention policy.  
Cycle fit: New service called after ingestion commit.

4. Watchlist-scoped live shock alerts  
Value: Real-time in-game risk/change detection for Pro watchlists.  
Effort: 1-2 weeks.  
Data needed: Live odds endpoint or event-level odds endpoint for in-play events.  
Storage: Reuse `odds_snapshots` with `is_live` metadata (or new column), plus `signals` type `LIVE_SHOCK`.  
Computations: Delta thresholds over short windows, shock severity, cooldown dedupe.  
API cost impact: Moderate to high; bounded via watchlist scope, interval tiers, and request budget caps.  
Dependencies/risks: Coverage variability and provider latency.  
Cycle fit: Add optional live sub-cycle in poller gated by `ODDS_API_LIVE_ENABLED`.

5. Historical close ingestion + CLV tracker  
Value: Quantifies edge quality and builds institutional trust (signal outcome analytics).  
Effort: 1-2 weeks.  
Data needed: Historical odds/closing-line endpoint.  
Storage: New `closing_lines` (or `market_close_snapshots`) and `clv_records`.  
Computations: Signal reference line vs close line delta, per-market CLV aggregates.  
API cost impact: Low daily if incremental, medium during backfill.  
Dependencies/risks: Historical endpoint shape/availability and matching event IDs consistently.  
Cycle fit: Daily job path in poller (or separate lightweight worker task).

6. Player props ingestion foundation  
Value: Opens major paid analytics surface and future model-ready data lake.  
Effort: 1-2 weeks (foundation only).  
Data needed: Props markets (points/rebounds/assists/PRA/3PM etc.) by book.  
Storage: New `props_snapshots` table; optional normalized `player_dim` mapping later.  
Computations: Consensus prop line/price and book deviation baselines.  
API cost impact: High unless narrowed to top props and watchlist scope.  
Dependencies/risks: Inconsistent player naming and sparse bookmaker coverage.  
Cycle fit: Optional enrichment pass only for near-tipoff watchlisted events.

7. Player props mispricing radar (phase 2)  
Value: High monetization potential but model-dependent.  
Effort: >2 weeks (depends on projection inputs).  
Data needed: Props snapshots + external projections/injury model.  
Storage: `props_signals` or `signals` extension with model confidence metadata.  
Computations: Fair-value model vs market line, confidence filters.  
API cost impact: Medium-high.  
Dependencies/risks: Projection quality and explainability requirements.  
Cycle fit: Separate model pipeline; not for immediate MVP extension.

---

## Deliverable D — Recommended Roadmap (Now / Next / Later)

## Now (0-3 weeks)
1. Consensus/dispersion persistence.
2. Dislocation signal type + Discord formatting.
3. Steam detection v2 using current snapshots only.
4. Minimal intel API endpoints for machine-readable packaging (no UI rewrite required).

## Next (3-6 weeks)
1. Watchlist-scoped live shock alerts with strict budget controls.
2. Historical close ingestion and CLV computations.
3. Daily/weekly Discord summary for Pro operators (optional digest mode).

## Later (6+ weeks)
1. Player props ingestion foundation at controlled scope.
2. Props mispricing radar once projection feed/model is available.
3. Cross-sport generalization after NBA pipeline stabilizes.

---

## Public API / Interface / Type Changes (Planned)

## Backend API additions
1. `GET /api/v1/intel/consensus?event_id={id}&market={market}`
2. `GET /api/v1/intel/dislocations?event_id={id}`
3. `GET /api/v1/intel/signals?event_id={id}&types=DISLOCATION,STEAM,MOVE`
4. Optional PR5: `GET /api/v1/intel/clv?event_id={id}` and `GET /api/v1/intel/clv/summary?days=7`

## Signal types expansion
- Add string values (no enum migration required): `DISLOCATION`, `STEAM`, `LIVE_SHOCK`, optional `CLV_EVENT`.

## New internal types (service contracts)
1. `NormalizedQuote`
- `event_id`, `commence_time`, `sport_key`, `sportsbook_key`, `market`, `outcome_name`, `line`, `price`, `is_live`, `fetched_at`
2. `ConsensusPoint`
- `event_id`, `market`, `outcome_name`, `consensus_line`, `consensus_price`, `dispersion`, `books_count`, `fetched_at`
3. `DislocationCandidate`
- `event_id`, `market`, `book`, `consensus_value`, `book_value`, `edge_score`, `direction`
4. `CLVRecord`
- `event_id`, `market`, `reference_value`, `closing_value`, `delta`, `created_at`

---

## Deliverable E — PR Plan (No Big Rewrite)

## PR1 — Odds API client extension + parsing + minimal caching
Scope:
- Extend client for reusable endpoint methods and safe retries without changing current behavior.
Files to extend:
- `backend/app/services/odds_api.py`
- `backend/app/core/config.py`
- `backend/app/tasks/poller.py` (optional logging counters only)
Recommended new files:
- `backend/app/services/odds_normalizer.py`
- `backend/tests/test_odds_api_parser.py`
- `backend/tests/test_odds_api_retry_backoff.py`
Config additions:
- `ODDS_API_HTTP_TIMEOUT_SECONDS=25`
- `ODDS_API_RETRY_ATTEMPTS=3`
- `ODDS_API_RETRY_BACKOFF_SECONDS=0.5`
- `ODDS_API_MAX_EVENTS_PER_CYCLE=40`
Acceptance:
- Existing flow unchanged by default.
- Parser handles missing/partial bookmaker markets safely.
- Retry path logs structured warning and fails gracefully.

## PR2 — Snapshot storage extension + consensus computation
Scope:
- Persist consensus/dispersion snapshots derived from existing `odds_snapshots`.
Files to extend:
- `backend/app/services/ingestion.py` (hook point after commit)
- `backend/app/services/market_data.py` (optionally consume consensus table for API responses)
Recommended new files:
- `backend/app/models/market_consensus_snapshot.py`
- `backend/app/services/consensus.py`
- `backend/app/schemas/intel.py`
- `backend/app/api/routes/intel.py`
- `backend/alembic/versions/<rev>_add_market_consensus_snapshots.py`
- `backend/tests/test_consensus.py`
Acceptance:
- Consensus rows written each cycle for tracked markets.
- No added external API calls.
- Endpoint returns deterministic consensus and dispersion metrics.

## PR3 — Dislocation alerts + Discord formatting
Scope:
- Add `DISLOCATION` signal generation and route through existing Discord preferences.
Files to extend:
- `backend/app/services/signals.py`
- `backend/app/services/discord_alerts.py`
- `backend/app/services/market_data.py` (surface new signals)
Recommended new files:
- `backend/tests/test_dislocation_rules.py`
- `backend/tests/test_discord_alert_payloads.py`
Optional schema extension:
- Add `alert_dislocation` boolean to `discord_connections` only if separate user toggle is required.
Acceptance:
- Dislocation signals generated from existing snapshots with explainable metadata.
- Discord message includes book vs consensus details.
- Free-tier redaction remains enforced.

## PR4 — Line movement v2 + steam alerts
Scope:
- Add `STEAM` signal type with stricter multi-book + velocity logic.
Files to extend:
- `backend/app/services/signals.py`
- `backend/app/core/config.py`
Recommended new files:
- `backend/tests/test_steam_rules.py`
Config additions:
- `STEAM_WINDOW_MINUTES=3`
- `STEAM_MIN_BOOKS=4`
- `STEAM_MIN_MOVE_SPREAD=0.5`
- `STEAM_MIN_MOVE_TOTAL=1.0`
Acceptance:
- Existing `MOVE`, `KEY_CROSS`, `MULTIBOOK_SYNC` behavior preserved.
- New steam signal is explainable and deduped.
- API and Discord include new signal type without regressions.

## PR5 (Optional) — Historical close + CLV reporting
Scope:
- Ingest closing lines and compute CLV per signal/event/market.
Files to extend:
- `backend/app/tasks/poller.py` (daily job hook)
- `backend/app/services/market_data.py` (optional CLV summary)
Recommended new files:
- `backend/app/models/closing_line.py`
- `backend/app/models/clv_record.py`
- `backend/app/services/historical.py`
- `backend/app/services/clv.py`
- `backend/alembic/versions/<rev>_add_closing_lines_and_clv.py`
- `backend/tests/test_clv.py`
Config additions:
- `ODDS_API_HISTORICAL_ENABLED=false`
- `ODDS_API_HISTORICAL_LOOKBACK_DAYS=7`
- `CLV_REPORT_CRON_UTC=0 5 * * *` (or simple hourly check guard in worker loop)
Acceptance:
- CLV records populate for settled games with close lines available.
- Summary endpoint returns per-market CLV aggregates.

---

## Minimal Docs / Tests / Config Additions (Production-Oriented)

## Docs
1. Add `docs/odds-api-full-access-roadmap.md` with endpoint map, cost model, and feature flags.
2. Update `README.md` with new env vars and `intel` endpoints.
3. Add `docs/ops-kpis.md` for cycle-level monitoring expectations.

## Tests
1. Parser robustness tests for malformed markets/books.
2. Deterministic rule tests for dislocation and steam thresholds.
3. Alert formatting tests for new signal types.
4. Optional integration test for end-to-end cycle with mocked Odds API payloads.

## Config/ops
1. Add feature flags for live/historical/props modules (default off).
2. Add per-feature request budget caps.
3. Log cycle KPIs consistently:
- requests_used_delta
- requests_last
- snapshots_inserted
- consensus_points_written
- signals_created_by_type
- alerts_sent/failed

---

## Risks and Mitigations

1. API cost blowups from live/props endpoints  
Mitigation: watchlist scope, interval tiers, strict feature flags, budget caps, dynamic disable on low credits.
2. Bookmaker naming inconsistencies  
Mitigation: canonical bookmaker map + unknown-key quarantine logs.
3. Partial endpoint coverage for props/historical  
Mitigation: coverage checks per cycle and graceful fallback to base markets.
4. Signal noise during thin markets  
Mitigation: min books filters, spread/total specific floors, cooldown dedupe.
5. Storage growth from added snapshots  
Mitigation: retention per table, selective write rules, indexed time windows.
6. Provider instability (429/5xx)  
Mitigation: retry/backoff/circuit-break behavior and degraded-mode logging.
7. Explainability drift as signals expand  
Mitigation: metadata schema contracts for every signal type and docs/tests on payload fields.

---

## Assumptions and Defaults Chosen
1. Preserve existing ingest endpoint behavior and cadence as baseline.
2. New high-ROI features should avoid incremental API requests where possible.
3. Live and historical features are feature-flagged and disabled by default until validated.
4. Existing `signals` table remains canonical for alert-triggering events.
5. No major frontend rewrite; new value is exposed via existing dashboard/game APIs and Discord outputs.
6. Backtesting is out of scope for immediate roadmap and remains maturity 0.

---

## Maintainer Execution Checklist

1. Merge PR1 and verify baseline ingestion parity (no behavior regression).
2. Merge PR2 and verify consensus rows and new intel endpoint responses.
3. Merge PR3 and verify dislocation signal generation plus Discord alert payloads.
4. Merge PR4 and verify steam triggers with unit tests and low-noise thresholds in staging.
5. Enable live feature flag in staging only and validate request burn before production.
6. If historical access is confirmed, merge PR5 and validate CLV summary consistency.
7. Update docs/env templates after each PR and keep feature flags default-safe.
8. Add cycle KPI alerts (log-based or Sentry-based) before enabling live/historical in production.
