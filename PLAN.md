# Stratum Sports Plan

## 1) Executive Summary
Stratum has pivoted from a premium betting product to a **Market Intelligence Infrastructure Layer**. 

The core system now supports real-time signal distribution via a high-performance **Webhook Delivery Engine**, institutional-grade usage metering, and the "Infrastructure" pricing tier.

The highest-leverage path forward is:
1. Live-shock hardening + channel policy split for public vs private alert surfaces.
2. Historical/aggregate partner API v1 for external backtesting and conversion.
3. Pro digest summaries to increase non-realtime engagement and retention.
4. Player props ingestion foundation under strict cost and reliability guardrails.

This sequence maximizes monetizable analytics value while controlling API spend and preserving reliability.

---

## 1.1) Recent Shipments (2026-02-26)
### V1 Structural Core Exposure Gate (shipped)
- Branch: `feature/v1-structural-core-gate`
- Commit: `fcf6d5ff3b6b1e49536e66c42ce1932d519285df`
- Scope delivered:
  1. Public exposure is gated by `public_structural_core_mode=true` (default ON).
  2. Public-facing feeds now expose structural-core rows only:
     - `signal_type == KEY_CROSS`
     - `market == spreads`
     - `strength_score >= 55`
     - `min_samples >= 15` when sample data exists (graceful skip/log when absent).
  3. User-facing relabel added without DB enum change:
     - `display_type = "STRUCTURAL THRESHOLD EVENT"` for `KEY_CROSS`.
  4. Discord dispatch is filtered to structural-core when mode is ON.
  5. Public/dashboard/game signal surfaces consume the same gate.
  6. Introspection utility added:
     - `scripts/trace_signal_feed.py`
     - `scripts/README.md` usage docs.
  7. Tests added/updated:
     - `backend/tests/test_public_structural_core_gate.py`
     - `backend/tests/test_performance_intel.py`
     - `backend/tests/test_discord_alert_payloads.py` coverage retained/passing in targeted run.

### Immediate follow-ups
1. Confirm full DB-backed test suite in CI (local run requires test DB host `db`).
2. Decide whether to apply structural-core gating to additional analytics endpoints (`/intel/signals/*`) or keep them as internal/pro analytics surfaces.
3. Frontend can prefer `display_type` over `signal_type` for user copy consistency.

## 1.2) Recent Shipments (2026-02-27)

### PR5 — Regime layer (shipped)
- Commit: `b8c2ba5`
- Scope: 2-state Gaussian HMM regime detection (stable/unstable), metadata-only enrichment on signals, feature-flagged OFF by default.
- Files: 8 new files in `backend/app/regime/`, model + migration for `regime_snapshots`, integration in `poller.py`.
- Tests: 17 tests covering feature extraction, HMM inference, config, metadata attachment, feature-flag OFF.

### Phase B remainder — Per-key usage endpoints (shipped)
- Commit: `64eee49`
- Scope: `get_key_current_usage()` and `get_key_usage_history()` service functions + 2 admin endpoints for per-key usage visibility.
- Files: `api_usage_tracking.py`, `admin.py`.

### M4 — API plan checkout, webhook entitlement sync, partner billing (shipped)
- Commit: `d3da3b6`
- Scope: API plan checkout endpoint (monthly/annual), webhook price-ID routing to sync `ApiPartnerEntitlement` independently from Pro subscriptions, partner self-serve billing summary + usage history + Stripe portal endpoints.
- Files: `config.py`, `stripe_service.py`, `billing.py`, `partner.py`.

### M5 — Launch hardening (shipped)
- Commit: `73738c4`
- Scope: `X-RateLimit-*` headers on all responses from global rate limiter, per-partner 60 req/min rate limiting with `X-Partner-RateLimit-*` headers, usage anomaly alerting at configurable thresholds (80/90/100%) with optional Discord alert, structured lifecycle logging across webhook processing and entitlement state transitions.

### M6 — Infrastructure Pivot (shipped)
- Commit: `infrastructure-pivot-HEAD`
- Scope: **Real-time Webhook Delivery Engine** with HMAC-SHA256 signing, partner self-serve webhook management, sales-focused 90% usage anomaly alerting, and updated Infrastructure-grade pricing defaults ($149/mo, 50k requests, 120 req/min).
- Files: `api_partner_webhook.py`, `webhook_delivery.py`, `partner.py`, `poller.py`, `stripe_meter_publisher.py`, `config.py`.
- New Tools: `backend/scripts/test_webhook.py` CLI utility.

---

## Stratum API Product Definition (Identity: Infrastructure)
- **What it is:** The institutional backbone for real-time betting signal distribution.
- **Primary consumers:** Quantitative funds, betting SaaS builders, and high-frequency syndicates.
- **Core value:** Real-time push delivery (Webhooks) of structured market intelligence.
- **Differentiator:** Signal speed + delivery flexibility + institutional transparency.
- **Commercial model:** 
  - **Builder:** $49/mo (10k requests).
  - **Pro Infra:** $149/mo (50k requests).
  - **Enterprise:** Custom (Contract).
- **Overage:** $2.00 per 1,000 requests.
- **Operator stance:** reliability, auditability, and explainability over opaque black-box outputs.

---

## 2) Current System Baseline

### 2.1 Module Map
| Module | Responsibility | Key locations |
|---|---|---|
| Runner / scheduler | Polling loop, adaptive cadence, lock, cleanup | `backend/app/tasks/poller.py` (`main`, `run_polling_cycle`, `determine_poll_interval`) |
| Odds fetch client | External API calls + request-credit header parsing | `backend/app/services/odds_api.py` (`OddsApiClient.fetch_nba_odds`) |
| Ingestion engine | Normalize, dedupe, persist snapshots, publish realtime updates | `backend/app/services/ingestion.py` (`ingest_odds_cycle`) |
| Signal engine | Movement detection, key-cross, multibook sync, dislocation, steam, live-shock, exchange divergence | `backend/app/services/signals.py` (`detect_market_movements`, `compute_strength_score`) |
| Alert routing | Pro watchlist + Discord preference filtering + send | `backend/app/services/discord_alerts.py` (`dispatch_discord_alerts_for_signals`) |
| Data shaping for UI/API | Consensus views, chart series, game detail assembly | `backend/app/services/market_data.py` (`build_dashboard_cards`, `build_game_detail`) |
| Context framework | Stub analytics for injuries/props/pace | `backend/app/services/context_score/*` |
| Persistence | SQLAlchemy models + Alembic migrations | `backend/app/models/*`, `backend/alembic/versions/0001_initial.py` |
| API surface | Auth, dashboard, games, watchlist, billing, Discord, websocket | `backend/app/api/routes/*`, `backend/app/api/router.py` |
| Security / ops | JWT auth, OAuth state hardening, rate limiting, structured logs | `backend/app/core/security.py`, `backend/app/core/rate_limit.py`, `backend/app/core/logging.py` |
| Frontend | Dashboard, game detail, watchlist, Discord settings, websocket client | `frontend/app/app/*`, `frontend/lib/useOddsSocket.ts` |
| Backtesting / research | Minimal/partial, not full productized workflow yet | Mixed (`backend/app/services/backtest.py`, tools) |

### 2.2 Current Polling Cycle (Fetch -> Transform -> Score -> Alert)
1. Worker loop starts in `backend/app/tasks/poller.py` and acquires Redis cycle lock (`redis_cycle_lock`).
2. Poller builds close-capture cadence and optional event scoping for near-tip games.
3. Poller calls `ingest_odds_cycle` in `backend/app/services/ingestion.py`.
4. Ingestion polls odds per configured sport key via `OddsApiClient.fetch_nba_odds`.
5. Payload normalizes into `OddsSnapshot` rows and `Game` upserts.
6. Redis dedupe key prevents duplicate snapshot inserts: `odds:last:{event}:{book}:{market}:{outcome}`.
7. Each inserted snapshot emits Pub/Sub `odds_updates` for realtime stream.
8. Ingestion computes and persists consensus snapshots (`market_consensus_snapshots`) when enabled.
9. Poller passes updated `event_ids` to `detect_market_movements`.
10. Signal engine computes `MOVE`, `KEY_CROSS`, `MULTIBOOK_SYNC`, `DISLOCATION`, `STEAM`, `LIVE_SHOCK`, and exchange divergence; then commits `Signal` rows.
11. Poller dispatches Discord alerts and partner webhooks for created signals.
12. A parallel live-watchlist loop polls only watchlisted live-window games and runs the same ingest/signal/alert path.
13. Scheduled jobs run in-loop: ops digest, historical backfill, CLV compute, usage flush, and retention cleanup.
14. Adaptive interval logic responds to provider request-budget headers and close-capture next-due timing.

### 2.3 Current Signal Rules and Alert Context
- Spread trigger: abs move `>= 0.5` or key-number cross (`NBA_KEY_NUMBERS`).
- Total trigger: abs move `>= 1.0`.
- Multibook trigger: `>= 3` books same direction in 5-minute window.
- Dislocation trigger: consensus-vs-book deltas with market-specific thresholds.
- Steam v2 trigger: velocity + synchronized move across at least 4 books in a 3-minute window.
- Live shock trigger: inplay/near-tip large movement thresholds over a short window (currently hard-coded; pending full config hardening).
- Exchange divergence: sportsbook-vs-exchange divergence signal path is implemented.
- Strength score: magnitude + speed + books, clamped to 1..100.
- Discord controls: `min_strength`, `alert_spreads`, `alert_totals`, `alert_multibook`, and per-connection threshold JSON (books/cooldown/dispersion).
- Current caveat: structural-core visibility gating is applied in Discord dispatch when `public_structural_core_mode=true`, which suppresses non-structural signal types in that channel.
- Context score exists but is currently scaffolded (`injuries`, `props`, `pace` proxies).

### 2.4 Persistence and State
**Postgres tables (core + intel):**
- `games`
- `odds_snapshots`
- `signals`
- `market_consensus_snapshots`
- `closing_consensus`
- `clv_records`
- `regime_snapshots`
- `watchlists`
- `discord_connections`
- `users`
- `subscriptions`
- `api_partner_entitlements`
- `api_partner_keys`
- `api_partner_usage_periods`
- `api_partner_webhooks`

**Redis keys/channels (core):**
- `poller:odds-ingest-lock`
- `poller:live-watchlist-lock`
- `odds:last:*`
- `signal:*`
- `odds_updates` (pub/sub)
- `ratelimit:{ip}:{minute}`
- `oauth:discord:state:{nonce}`

### 2.5 Current Config Surface
- Central settings: `backend/app/core/config.py` (`Settings`)
- Templates: `.env.example`, `.env.production.example`
- Key controls:
  - `ODDS_API_*`
  - Poll cadence and daily budget controls
  - Book/region/market filters + sport-key list
  - Consensus/dislocation/steam/CLV/backfill toggles and thresholds
  - Exchange divergence and regime feature flags
  - Structural-core exposure mode + time-bucket controls
  - Partner API limits (`partner_soft_limit_monthly`, `partner_rate_limit_per_minute`, overage)
  - `FREE_DELAY_MINUTES`
  - `FREE_WATCHLIST_LIMIT`

---

## 3) Maturity Snapshot

### 3.1 Capability Matrix
| Capability | Maturity (0-3) | Robustness notes | Gaps |
|---|---:|---|---|
| Data ingest (pregame odds) | 2 | Async poller, dedupe, upsert, retention cleanup | Single endpoint path only; no modular endpoint selection |
| Normalization | 2 | Stable schema for h2h/spreads/totals | No generalized normalizer for props/historical/live variants |
| Scoring/signals | 3 | Move/key-cross/multibook + dislocation + steam + live-shock + divergence all integrated | Live-shock config hardening + signal taxonomy consistency still pending |
| Alert routing | 2 | Discord + partner webhooks + threshold evaluation + cooldown support | Structural-core gating policy needs explicit channel separation; no customer digest pipeline yet |
| Persistence | 3 | Consensus + closing + CLV + regime persistence shipped | No props table/foundation yet |
| Scheduling/job coordination | 3 | Main loop + live-watchlist loop + backfill/CLV/digest jobs + adaptive cadence | Workload isolation and queueing still limited |
| Monitoring/ops | 2 | Health, structured logs, KPI writes, admin ops telemetry | No explicit SLO dashboard/error budgets yet |
| Docs/runbooks | 2 | README + deploy runbook + user guide | Missing full roadmap spec in one clean execution flow |
| Testing | 2 | Broad unit/integration coverage across signals/admin/billing/CLV/perf-intel | Live-shock loop integration and high-load partner history tests still missing |
| Backtesting/research | 1 | CLV/performance intel endpoints and exports shipped | Partner-facing historical contract for external backtests still pending |

### 3.2 Top Strengths
1. Strong ingestion-to-alert operational loop.
2. Efficient DB query patterns for dashboard and signal paths.
3. Cost-aware polling tied to real provider usage headers.
4. Backend-enforced tier gating.
5. Good modular boundaries across fetch/ingest/signal/alert/API layers.

### 3.3 Top Gaps
1. No production-hardened bounded watchlist live-shock path (partial implementation exists).
2. No explicit channel policy split for structural-core gating vs private Pro/API alert channels.
3. No partner-facing historical/aggregate API contract for backtesting.
4. No props foundation for phase-2 analytics expansion.
5. Observability is still below mature SaaS operations level.

---

## 4) Prioritized Product Opportunities

### 4.1 Ranking Rubric
- Monetizable analytics value
- Feasibility (target under 1-2 weeks per slice)
- Infra delta (lower is better)
- Explainability
- Cross-sport reusability

### 4.2 Ranked Opportunities
| Rank | Opportunity | Value | Feasibility | Infra delta | Explainability | Reuse | Total /25 | Tier |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Watchlist-scoped live-shock hardening + channel policy split | 5 | 4 | 4 | 5 | 4 | 22 | Tier 1 |
| 2 | Historical/aggregate partner API access (v1) | 5 | 3 | 4 | 5 | 4 | 21 | Tier 1 |
| 3 | Pro digest summaries (daily/weekly) | 4 | 4 | 4 | 4 | 4 | 20 | Tier 1 |
| 4 | Player props ingestion foundation | 4 | 3 | 2 | 4 | 5 | 18 | Tier 2 |
| 5 | Player props mispricing radar | 5 | 2 | 2 | 3 | 5 | 17 | Tier 3 |
| 6 | Cross-sport generalization (post-NBA hardening) | 4 | 2 | 3 | 4 | 5 | 18 | Tier 3 |

### 4.3 Candidate Scoping (Condensed)
1. **Live-shock hardening + channel policy split**
   - Value: protects API spend while unlocking high-signal inplay alerts.
   - Effort: 4-7 days.
   - Cost impact: low-medium with per-cycle guardrails.
2. **Historical/aggregate partner API access**
   - Value: enables partner-side backtesting and accelerates paid conversion.
   - Effort: 1-2 weeks.
   - Cost impact: low-medium (read-heavy query load; no new provider calls).
3. **Pro digest summaries**
   - Value: increases engagement and retention outside realtime sessions.
   - Effort: 4-6 days.
   - Cost impact: low.
4. **Props foundation**
   - Value: unlocks next monetization surface.
   - Effort: 1-2 weeks foundation only.
   - Cost impact: high unless tightly scoped.
5. **Props mispricing radar**
   - Value: high but model-dependent.
   - Effort: >2 weeks and additional data dependencies.
   - Cost impact: medium-high.

---

## 5) Roadmap (Now / Next / Later)

### 5.1 Now (0-3 weeks)
1. Live-shock hardening: feature flags, threshold config, and watchlist-loop burn controls.
2. Channel policy split: structural-core gating for public surfaces vs private Pro/API alert channels.
3. Historical/aggregate partner API endpoints v1 (`since/until/cursor` + aggregate buckets + metering).
4. Signal taxonomy consistency across APIs (`LIVE_SHOCK` filter support where appropriate).

### 5.2 Next (3-6 weeks)
1. Pro digest summaries pilot (daily/weekly webhook/email) with delivery SLOs.
2. Player props ingestion foundation (points/rebounds/assists) behind strict flags.
3. Observability hardening (SLO dashboard + alerting baselines for signal delivery and partner API).

### 5.3 Later (6+ weeks)
1. Props mispricing radar once projection inputs are available.
2. Cross-sport generalization after NBA stability is proven.
3. Historical/Aggregate API v2 (bulk export/materialized windows/cohort rollups).

### 5.4 Consolidated Expansion Track (Execution-Ready)
1. **Watchlist-scoped live shock alerts**
   - Current status: partial backend implementation exists (`backend/app/services/signals.py` `LIVE_SHOCK` + `backend/app/tasks/poller.py` `run_live_watchlist_loop`).
   - Gaps: explicit feature flag + thresholds, API burn controls, alert-path tests, and channel policy split for structural-core/public-gating vs private alerts.
   - Exit criteria: 7-day staging run with stable credit burn and acceptable false-positive rate.
2. **Historical/aggregate partner API endpoints (v1)**
   - Current status: internal intel surfaces exist (`/intel/clv/*`, `/intel/signals/*`) but no partner-facing historical contract.
   - Gaps: partner-key auth surfaces, pagination/time-range filters, aggregate buckets, explicit metering + rate-limit policy for heavier reads.
   - Exit criteria: partners can query 30-90 day historical windows and aggregate summaries with paid key auth.
3. **Pro digest summaries**
   - Current status: internal digest machinery exists (`backend/app/services/ops_digest.py`) and can be adapted.
   - Gaps: recipient/subscription model, entitlement checks, customer-facing templates, idempotent send tracking, delivery metrics.
   - Exit criteria: opt-in pilot cohort receives stable daily/weekly digests with delivery/error SLO tracking.
4. **Player props ingestion foundation**
   - Current status: current odds normalizer intentionally skips props markets; only proxy context scoring exists.
   - Gaps: canonical props schema, parser/normalizer support for points/rebounds/assists, retention/indexing strategy, guarded ingest flag.
   - Exit criteria: props snapshots ingest reliably for a narrow market set with parity tests and cost guardrails.

**Recommended execution order**
1. Live shock hardening.
2. Historical/aggregate API v1.
3. Pro digest summaries.
4. Props ingestion foundation.

---

## 6) Monetization API Product Plan

### 6.1 Commercial Decisions (Locked)
1. Paid API is a separate product line from web Pro access.
2. Subscriptions are independently purchasable: customers may buy Web Pro only, API only, or both.
3. No free trial for API plans.
4. Billing cadence includes monthly and annual options.
5. Stripe Tax is enabled for US-only sales initially.
6. Usage model is soft-limit + paid overage (not hard cutoff).

### 6.2 Packaging and Price Model
1. **Infrastructure Monthly (default)**
   - Base price: `$149/month`.
   - Includes `50,000` monthly requests and infrastructure webhook access.
2. **Infrastructure Annual**
   - Annual prepay version of Infrastructure access.
   - Includes annual usage allowance and overage billing.
3. **Optional Builder entry plan**
   - `$49/month` with lower included request allowance (typically `10,000`).
   - Can be positioned as a lower-throughput onboarding tier.
4. **Overage**
   - Metered billing above included allowance.
   - Charged per usage unit (e.g., per 1,000 API calls) on monthly invoice.
5. **Plan boundaries**
   - Web Pro and API Partner remain distinct entitlements and separate billing products.
   - Accounts can hold one or both products.

### 6.3 Entitlements and Access Control
1. Add explicit API entitlement state per account:
   - `api_access_enabled`
   - `api_plan_code` (`api_monthly`, `api_annual`) in current schema; tier-specific codes can be added in a follow-up migration.
   - `api_usage_soft_limit`
   - `api_overage_rate`
2. API access requires:
   - active Stripe subscription status
   - at least one active API key
   - account in good standing (not suspended)
3. Keys are scoped to partner account, never to shared internal token.
4. Existing web auth/JWT remains unchanged for app UI; partner API uses token/key auth.

### 6.4 Usage Metering and Overage Flow
1. Define billable usage unit:
   - default: `request_count` on paid Intel endpoints.
2. Track usage counters per key and per billing period:
   - period start/end
   - included units
   - used units
   - overage units
3. Stripe meter events are emitted asynchronously from backend usage logs.
4. Soft-limit behavior:
   - continue serving responses after limit is crossed
   - add response headers for `usage`, `remaining`, and `overage_to_date`
   - optional warning webhooks/email notifications at 80%, 100%, 120%
5. Fail-safe:
   - if Stripe metering transiently fails, queue and retry; do not block API request path.

### 6.5 Stripe Configuration Requirements
1. Products/prices:
   - `stratum_api_monthly`
   - `stratum_api_annual`
   - `stratum_api_overage` (metered)
2. Customer model:
   - one Stripe customer per Stratum account.
3. Billing portal:
   - customers can manage payment method and subscription.
4. Webhook events required:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
5. Tax setup:
   - Stripe Tax enabled
   - US-only collection policy and state rules configured.

### 6.6 API Surface for Partner Product
1. Public partner endpoints (paid):
   - ranked signal feed with quality filters
   - optional consensus/dislocation/CLV views per plan level
2. Partner lifecycle endpoints (admin/internal):
   - create/revoke/rotate API key
   - read usage summary
   - read current plan + overage status
3. Required filters and controls for paid feed:
   - `time_bucket`
   - `since`
   - `min_score`
   - `velocity_gt`
   - `type/signal_type`
4. Backward compatibility requirement:
   - nullable-safe response fields
   - additive-only schema changes for existing clients.

## Composite Score Interpretation (v1)
Composite Score is a deterministic ranking heuristic for prioritization, not a probability of winning.
Tier labels represent operational priority bands, not predictive certainty.

- v1 uses a rules/weights heuristic and no ML model.
- Tiers are operational priority bands:
  - High: `>= 75`
  - Medium: `55-74`
  - Low: `< 55`
- Backtest and summary views should expose `score_source` so operators can distinguish:
  - `composite` (enriched score)
  - `strength_fallback` (legacy fallback)
- CLV calculation pipeline is unchanged by enrichment.

### 6.7 Rate Limiting, Quotas, and SLA Boundaries
1. Enforce per-key rate limits separate from public/IP limits.
2. Return standard limit headers:
   - `X-RateLimit-Limit`
   - `X-RateLimit-Remaining`
   - `X-RateLimit-Reset`
3. Distinguish:
   - short-window technical rate limits (429 protection)
   - billing-period soft usage limits (overage billing)
4. Define support/SLA policy by plan:
   - response target
   - uptime target
   - incident communication channel.

### 6.8 Implementation Sequence (Monetization Track)
1. **Phase M1: Commercial plumbing** — SHIPPED
   - Stripe products/prices/meter setup
   - entitlement fields + webhook sync
2. **Phase M2: Partner key management** — SHIPPED
   - key issuance/revocation/rotation
   - per-key usage counters + logs
3. **Phase M3: Usage billing** — SHIPPED (`b6a7e87`)
   - meter event publisher + retry queue
   - overage calculation and invoice validation
4. **Phase M4: Customer experience** — SHIPPED (`d3da3b6`)
   - API plan checkout (monthly/annual) + billing portal
   - usage/overage visibility in app (billing-summary, usage/history, portal endpoints)
   - webhook price-ID routing for API vs Pro subscription independence
5. **Phase M5: Launch hardening** — SHIPPED (`73738c4`)
   - X-RateLimit-* headers on all responses + per-partner 60 req/min rate limiting
   - usage anomaly alerting at configurable thresholds (80/90/100%) with Discord notifications
   - structured lifecycle logging for webhook processing + entitlement state transitions (provisioned/restored/suspended)

### 6.9 Monetization Acceptance Criteria
1. A customer can purchase API monthly or annual plan via Stripe.
2. API entitlement enables/disables automatically from subscription state.
3. Usage is metered by key and visible internally.
4. Over-limit traffic is served and billed as overage.
5. Failed payment transitions account out of paid API access per policy.
6. All partner API responses remain backward-compatible and nullable-safe.

## API Usage Policy (v1)
- Acceptable use includes internal tools, dashboards, automation, and analytics workflows.
- Reselling, rebroadcasting, or syndicating API outputs requires a separate commercial agreement.
- Access is subject to rate limits, traffic heuristics, and abuse monitoring.
- Automation is permitted when clients respect limits and retry discipline.
- Abuse, credential sharing, scraping misuse, or policy evasion can result in suspension or termination.
- Enforcement is implemented via API keys, rate limits, anomaly detection, and audit logging.

## Release Governance (v1)
- Versioning policy favors additive updates by default.
- Breaking changes require an explicit API version bump.
- Deprecation window target for breaking removals is minimum 30 days.
- Changelog of record lives in `CHANGELOG.md` (or equivalent repository release log).
- Rollout discipline stays staging -> verification -> production promotion.

---

## 7) Engineering Rollout Plan (Micro-PRs)

### PR1 — Odds API client extension + parsing + minimal caching
**Scope**
- Extend endpoint methods and safe retries with no default behavior change.

**Files**
- `backend/app/services/odds_api.py`
- `backend/app/core/config.py`
- `backend/app/tasks/poller.py` (logging counters only, optional)
- New: `backend/app/services/odds_normalizer.py`
- New tests: `backend/tests/test_odds_api_parser.py`, `backend/tests/test_odds_api_retry_backoff.py`

**Config**
- `ODDS_API_HTTP_TIMEOUT_SECONDS=25`
- `ODDS_API_RETRY_ATTEMPTS=3`
- `ODDS_API_RETRY_BACKOFF_SECONDS=0.5`
- `ODDS_API_MAX_EVENTS_PER_CYCLE=40`

**Acceptance**
1. Existing flow unchanged by default.
2. Parser handles missing/partial markets safely.
3. Retry path logs structured warnings and fails gracefully.

### PR2 — Snapshot storage extension + consensus computation
**Scope**
- Persist consensus/dispersion snapshots from existing `odds_snapshots`.

**Files**
- `backend/app/services/ingestion.py`
- `backend/app/services/market_data.py` (optional consumption path)
- New model: `backend/app/models/market_consensus_snapshot.py`
- New service: `backend/app/services/consensus.py`
- New schemas/routes: `backend/app/schemas/intel.py`, `backend/app/api/routes/intel.py`
- Migration: `backend/alembic/versions/<rev>_add_market_consensus_snapshots.py`
- Tests: `backend/tests/test_consensus.py`

**Acceptance**
1. Consensus rows are written each cycle for tracked markets.
2. No incremental external API requests.
3. Endpoint returns deterministic consensus + dispersion metrics.

### PR3 — Dislocation alerts + Discord formatting
**Scope**
- Add `DISLOCATION` signal generation and route through existing Discord preference system.

**Files**
- `backend/app/services/signals.py`
- `backend/app/services/discord_alerts.py`
- `backend/app/services/market_data.py`
- Tests: `backend/tests/test_dislocation_rules.py`, `backend/tests/test_discord_alert_payloads.py`
- Optional schema: `alert_dislocation` on `discord_connections` if separate toggle is required.

**Acceptance**
1. Dislocation signals generated with explainable metadata.
2. Discord payload includes book-vs-consensus details.
3. Free-tier redaction remains enforced.

### PR4 — Line movement v2 + steam alerts
**Scope**
- Add `STEAM` with stricter multi-book + velocity rules.

**Files**
- `backend/app/services/signals.py`
- `backend/app/core/config.py`
- Tests: `backend/tests/test_steam_rules.py`

**Config**
- `STEAM_WINDOW_MINUTES=3`
- `STEAM_MIN_BOOKS=4`
- `STEAM_MIN_MOVE_SPREAD=0.5`
- `STEAM_MIN_MOVE_TOTAL=1.0`

**Acceptance**
1. Existing `MOVE`, `KEY_CROSS`, `MULTIBOOK_SYNC` behavior preserved.
2. New steam signals are explainable and deduped.
3. API and Discord include new type without regressions.

### PR5 — Regime layer (metadata-only, feature-flagged) — SHIPPED
**Status:** Completed. Commit `b8c2ba5`.

**Scope**
- Add a modular 2-state regime model (`stable`, `unstable`) that runs alongside the current pipeline.
- Keep existing signal detection/classification untouched.
- Keep existing naming and terminology untouched (`signals`, `moves`, `context_score`, `confidence`, etc.).
- Attach regime data only as optional metadata under `signal["meta"]["regime"]`.

**Files**
- New package: `backend/app/regime/`
  - `config.py`
  - `features.py`
  - `hmm.py`
  - `service.py`
  - `metrics.py`
  - `tests/test_regime.py`
- Integration points:
  - `backend/app/core/config.py` (feature flag)
  - `backend/app/tasks/poller.py` (metadata attachment between exchange divergence and Discord alerts)
- Persistence:
  - New model `backend/app/models/regime_snapshot.py`
  - Migration `backend/alembic/versions/j4d5e6f7g8h9_add_regime_snapshots.py`

**Config**
- `REGIME_DETECTION_ENABLED=false` (default)

**Acceptance**
1. With flag OFF, output schemas and behavior remain unchanged.
2. With flag ON, regime metadata appears only at `meta.regime` and does not alter existing top-level fields.
3. Regime output contract:
   - `regime_label`
   - `regime_probability`
   - `transition_risk`
   - `stability_score`
   - `model_version`
4. Unit tests cover feature extraction, deterministic inference, and feature-flag OFF behavior.

### PR6 — Historical close + CLV reporting — SHIPPED
**Status:** Completed. Full CLV pipeline implemented across backend services, models, API endpoints, frontend, and tests.

**Scope delivered:**
1. Closing consensus derivation from final pre-commence odds (`backend/app/services/closing.py`).
2. CLV computation comparing signal entry lines against closing lines (`backend/app/services/clv.py`).
3. Historical backfill service for games that commenced during poller downtime (`backend/app/services/historical_backfill.py`).
4. Performance intel aggregation with trust scorecards and stability analysis (`backend/app/services/performance_intel.py`).
5. Models: `ClosingConsensus`, `ClvRecord` with migrations.
6. API endpoints: 6 CLV endpoints under `/intel/clv/*` (summary, recap, scorecards, records, teaser, CSV export).
7. Poller integration: automatic backfill + CLV computation timers in polling cycle.
8. Frontend: full performance page, types, API functions.
9. Tests: ~3000 lines across `test_closing.py`, `test_clv.py`, `test_historical_backfill.py`, `test_performance_intel.py`.

### PR7 — Watchlist-scoped Live Shock hardening
**Status:** PARTIAL IN CODE; pending production hardening.

**Scope**
1. Keep live-shock generation scoped to watchlist-tracked live games only.
2. Add explicit feature flags + configurable thresholds to avoid hard-coded criteria.
3. Add budget/safety controls (per-cycle max games, max extra requests, kill-switch).
4. Define structural-core interaction policy so private Pro/API channels can receive intended live-shock alerts without reopening public feeds.

**Files**
- `backend/app/services/signals.py`
- `backend/app/tasks/poller.py`
- `backend/app/services/discord_alerts.py`
- `backend/app/core/config.py`
- Tests: `backend/tests/test_live_shock_rules.py`, `backend/tests/test_live_watchlist_loop.py`, `backend/tests/test_discord_alert_payloads.py`

**Config**
- `LIVE_SHOCK_ENABLED=false`
- `LIVE_SHOCK_WINDOW_MINUTES=5`
- `LIVE_SHOCK_MIN_MOVE_SPREAD=4.5`
- `LIVE_SHOCK_MIN_MOVE_TOTAL=6.5`
- `LIVE_SHOCK_MIN_ML_PROB_DELTA=0.15`
- `LIVE_WATCHLIST_LOOP_INTERVAL_SECONDS=60`
- `LIVE_WATCHLIST_MAX_GAMES_PER_CYCLE=25`

**Acceptance**
1. Live-shock alerts are emitted only for watchlist games in the live window.
2. Request burn remains within configured per-cycle/per-day bounds.
3. No regressions to existing signal generation and Discord/webhook delivery.

### PR8 — Historical/Aggregate Partner API endpoints (v1)
**Status:** PLANNED.

**Scope**
1. Add partner-facing historical signal query endpoint with `since`, `until`, `signal_type`, `market`, `min_score`, `limit`, `cursor`.
2. Add aggregate bucket endpoint (daily/weekly counts, avg strength, CLV rollups where available).
3. Wire endpoint usage into existing API metering and partner rate-limit headers.

**Files**
- `backend/app/api/routes/partner.py`
- `backend/app/services/performance_intel.py`
- `backend/app/services/api_usage_tracking.py`
- `backend/app/schemas/partner.py` (new/extended)
- Tests: `backend/tests/test_partner_historical_api.py`

**Acceptance**
1. Partners can backtest with stable paginated historical windows.
2. Aggregate output is deterministic for identical query ranges.
3. Heavy historical reads are metered and rate-limited separately from webhook push path.

### PR9 — Pro Digest Summaries
**Status:** PLANNED.

**Scope**
1. Add user/partner digest subscription preferences (daily/weekly, destination, enabled state).
2. Build digest payloads from existing intel/performance services (top CLV signals, win-rate proxies, anomalies).
3. Add idempotent scheduler + send tracking + retry path.

**Files**
- `backend/app/services/ops_digest.py` (shared internals)
- `backend/app/services/pro_digest.py` (new)
- `backend/app/models/pro_digest_subscription.py` (new)
- `backend/app/models/pro_digest_sent.py` (new)
- `backend/app/api/routes/partner.py` and/or `backend/app/api/routes/billing.py`
- Tests: `backend/tests/test_pro_digest.py`

**Acceptance**
1. Opted-in recipients receive exactly one digest per configured cadence window.
2. Digest send failures are observable and retryable without duplicate sends.
3. Free-tier redaction and paid entitlement boundaries are enforced.

### PR10 — Player Props ingestion foundation
**Status:** PLANNED (Later bucket).

**Scope**
1. Add narrow props ingest support for `player_points`, `player_rebounds`, `player_assists`.
2. Add canonical storage model and parser normalization for player identity, line, and price.
3. Keep behind feature flag and sport whitelist until request-cost profile is validated.

**Files**
- `backend/app/services/odds_api.py`
- `backend/app/services/ingestion.py`
- `backend/app/models/player_prop_snapshot.py` (new)
- `backend/alembic/versions/<rev>_add_player_prop_snapshots.py`
- `backend/app/core/config.py`
- Tests: `backend/tests/test_player_props_normalization.py`, `backend/tests/test_player_props_ingestion.py`

**Acceptance**
1. Props snapshots persist with deterministic schema and dedupe behavior.
2. Existing spreads/totals/h2h ingest path remains unchanged when flag is OFF.
3. Staging burn-rate telemetry proves the props scope is budget-safe before production enablement.

---

## 8) Admin Control Plane Roadmap (SaaS Operations)

### 8.1 Current State (Verified)
1. Admin read APIs are live (`/api/v1/admin/overview`, `/api/v1/admin/conversion/funnel`, `/api/v1/admin/audit/logs`, `/api/v1/admin/users`).
2. Admin mutation APIs are live for user access (`tier`, `role`, `active`, password reset) with reason + step-up + confirm phrase.
3. Billing admin mutations are live (`resync`, `cancel`, `reactivate`) with immutable audit entries.
4. API partner key lifecycle is live (`issue`, `rotate`, `revoke`) with one-time key reveal and audit traceability.
5. Admin UI now supports core mutation flows and audit visibility, but does not yet cover full ops controls, entitlement management, or MFA governance.

### 8.2 Phase A (P0) — Admin foundations
1. Replace binary `is_admin` with scoped roles:
   - `super_admin`, `ops_admin`, `support_admin`, `billing_admin`
2. Add role permission checks per endpoint/action.
3. Add immutable admin audit log:
   - actor user id, action type, target, before/after payload, reason, request id, created at
4. Require step-up auth for sensitive admin writes.

**Acceptance**
1. Every admin write creates an audit record.
2. Unauthorized roles are blocked.
3. Sensitive actions require step-up auth.

**Status**
1. Completed for current admin mutation surfaces.
2. Remaining: periodic role/access review automation and privileged-session hardening (tracked in Phase E).

### 8.3 Phase B (P0) — Core admin mutation APIs
1. User management APIs:
   - list/search users
   - update tier
   - grant/revoke admin
   - activate/deactivate account
   - initiate password reset
2. Billing admin APIs:
   - view Stripe customer/subscription
   - resync billing state
   - temporary grace controls
   - cancel/reactivate with audit reason
3. Partner API admin APIs:
   - issue/revoke/rotate keys
   - set plan and limits
   - view key usage/overage

**Acceptance**
1. Routine admin operations are no longer CLI-only.
2. Mutations enforce role + audit + reason.
3. Support workflows are executable in-app.

**Status**
1. Completed: user search + tier/role/active/password reset mutations.
2. Completed: billing resync/cancel/reactivate mutations.
3. Completed: partner API key issue/rotate/revoke lifecycle.
4. Completed: partner entitlement plan/limit mutation APIs and key-level usage/overage views (`64eee49`, `d3da3b6`).
5. Phase B fully shipped.

### 8.4 Phase C (P1) — Admin UI expansion
1. Expand `/app/admin` into tabs:
   - Overview
   - Users
   - Billing
   - API Partners
   - Operations
   - Audit Log
2. Add destructive-action safeguards:
   - confirmation dialogs
   - typed confirmation for critical actions
   - inline diff preview for role/tier changes
3. Return action receipts:
   - action id
   - actor
   - timestamp
   - rollback hint where applicable

**Acceptance**
1. End-to-end support flows run from UI.
2. Every action maps to an audit entry.
3. Error states are actionable and safe.

**Status**
1. Tabbed admin console shipped: Overview, Users, Billing, API Partners, Operations, Audit, Security tabs with permission-scoped visibility.
2. Destructive-action safeguards shipped: step-up password + confirmation phrase + MFA for all mutations.
3. Action receipt display shipped: structured receipt card with action details + client-side timestamp for all mutations.
4. Outcomes report baseline-readiness indicator shipped: shows sample count vs 30 minimum when building.
5. CSV rate normalization shipped: rate fields exported as `55.0%` instead of raw `0.55`.
6. Phase C fully shipped.

### 8.5 Phase D (P1) — Ops and reliability controls
1. Replace single ops token with scoped service tokens.
2. Add token rotation and revocation flow.
3. Add admin run controls:
   - bounded backfill trigger
   - poller health diagnostics
   - alert replay tooling
4. Add admin-visible ops telemetry:
   - webhook failures
   - deploy status
   - queue/backfill status
   - API usage anomalies

**Acceptance**
1. Ops access is identity-scoped and revocable.
2. Operational interventions are auditable and permission-gated.
3. Admin dashboard surfaces current system risk.

**Status**
1. Scoped service tokens shipped: `OpsServiceToken` model, issue/revoke/rotate service, DB-backed auth with scope enforcement, static token backward compat, admin CRUD endpoints with step-up auth + audit logging, `ops_token_write` permission on `super_admin` + `ops_admin` roles.
2. Admin run controls shipped: backfill trigger (`POST /admin/ops/backfill/trigger`), poller health diagnostics (`GET /admin/ops/poller/health`), alert replay (`POST /admin/ops/alerts/replay`), ops telemetry aggregation (`GET /admin/ops/telemetry`). All endpoints permission-gated, step-up auth on mutations, audit logged.
3. Frontend Operations tab shipped: replaces stub Ops Tokens tab with 5-section layout (Poller Health, Backfill Trigger, Alert Replay, Ops Telemetry, Ops Tokens reference).
4. Phase D fully shipped.

### 8.6 Phase E (P2) — Security and compliance hardening
1. MFA for admin accounts.
2. Stronger password policy and breach-resistant controls.
3. Privileged session security:
   - shorter admin session TTL
   - forced re-auth on privilege elevation
4. Periodic access review workflow:
   - stale role detection
   - last-used timestamps

**Acceptance**
1. Admin auth meets baseline SaaS security expectations.
2. Privileged sessions are time-bounded and reviewable.
3. Admin role lifecycle is governed and visible.

**Status**
1. Completed: TOTP-based MFA for admin accounts (`pyotp`, enroll/confirm/disable/backup-codes lifecycle).
2. Completed: Two-phase MFA login (short-lived challenge JWT → TOTP verification → access token with `mfa: true` claim).
3. Completed: Admin session TTL enforcement (4h admin tokens vs 24h regular, via `extra_claims` on `create_access_token`).
4. Completed: MFA-gated step-up auth (all 14 admin mutation call sites verify TOTP when MFA is enabled).
5. Completed: `last_login_at` tracking for access review.
6. Completed: Frontend MFA login flow, admin Security tab (enroll/disable/regenerate backup codes), MFA code field on mutation controls.
7. Completed: Configurable password complexity policy (`validate_password_strength()` — min length, uppercase, lowercase, digit, special character). Enforced on registration and password reset. Public `GET /auth/password-policy` endpoint for frontend form display.
8. Completed: Stale admin detection endpoint (`GET /admin/access-review/stale`) — queries admins with NULL or old `last_login_at`, configurable threshold (default 30 days). Frontend stale admin table in Overview tab.
9. Phase E fully shipped.

### 8.7 Next Up (Immediate Execution Order)
1. ~~**PR-A:** Partner entitlement controls~~ — SHIPPED (`64eee49`, `d3da3b6`).
2. ~~**PR-B:** Partner usage visibility in admin~~ — SHIPPED (`d3da3b6`). Billing summary, usage history, and portal endpoints live.
3. ~~**PR-C:** Admin UI tab split and permission-scoped action surfaces (Users/Billing/API Partners/Audit).~~ — SHIPPED (`fca060b`).
4. ~~**PR-D:** Scoped ops service tokens with rotation/revocation and runbook-backed break-glass path.~~ — SHIPPED. DB-backed `OpsServiceToken` with scopes, admin CRUD, backward-compat static token fallback.
5. ~~**PR-E:** Admin MFA + privileged session TTL enforcement.~~ — SHIPPED. TOTP MFA lifecycle, two-phase login, 4h admin TTL, MFA-gated step-up auth, `last_login_at` tracking, frontend Security tab.
6. ~~**PR-F:** Phase D ops run controls + telemetry dashboard.~~ — SHIPPED. Backfill trigger, poller health, alert replay, ops telemetry, Operations tab with 5 sections.
7. ~~**PR-G:** Phase C remainders + Phase E security hardening tail.~~ — SHIPPED. Password complexity validation (configurable policy, public policy endpoint), stale admin detection, enriched mutation receipts, outcomes baseline-readiness indicator, CSV rate normalization. 236 tests pass.

### 8.8 Deferred Follow-Ups (Outcomes Report UX/Export)
1. ~~Add explicit baseline-readiness indicator in outcomes summary/export~~ — SHIPPED. Shows "Baseline building — N / 30 minimum samples" when `clv_samples < 30`.
2. ~~Normalize rate presentation in admin outcomes CSV/UI~~ — SHIPPED. `_fmt_rate()` formats rate fields as readable percentages (`55.0%`) in summary, by_signal_type, and by_market CSV tables.
3. Add optional summary metadata in exports to explain low-sample windows (current samples, baseline samples, minimum recommended sample size).
4. Keep outcome interpretation copy explicit: CLV-standard operational KPI, not guaranteed wagering outcome.

---

## 9) Test, Docs, and Ops Additions

### 9.1 Test plan additions
1. Parser robustness tests for malformed books/markets.
2. Deterministic rule tests for dislocation and steam thresholds.
3. Alert payload tests for new signal types.
4. Integration tests for end-to-end cycle with mocked provider payloads.
5. Admin API tests by role (success, forbidden, validation).
6. Audit integrity tests (before/after payloads).
7. Security tests for step-up + MFA enforcement.

### 9.2 Documentation plan
1. Add `docs/odds-api-full-access-roadmap.md`.
2. Add `docs/admin-control-plane.md`.
3. Update `docs/production-runbook.md`:
   - break-glass flow
   - token rotation
   - audit review cadence
4. Update `README.md` with new env vars and intel/admin feature surfaces.
5. Add `docs/ops-kpis.md` for cycle KPI expectations.

### 9.3 KPI logging expectations
- `requests_used_delta`
- `requests_last`
- `snapshots_inserted`
- `consensus_points_written`
- `signals_created_by_type`
- `alerts_sent`
- `alerts_failed`

---

## 10) Risks and Mitigations
1. **API cost spikes** from live/props expansion.  
   Mitigation: feature flags, watchlist scoping, request budgets, auto-throttle.
2. **Book naming inconsistencies.**  
   Mitigation: canonical bookmaker mapping + unknown-key quarantine logging.
3. **Sparse coverage in props/historical endpoints.**  
   Mitigation: per-cycle coverage checks + graceful fallback.
4. **Signal noise in thin markets.**  
   Mitigation: min-book filters, market-specific thresholds, cooldown dedupe.
5. **Storage growth from added snapshots.**  
   Mitigation: retention policy per table + selective writes + indexed windows.
6. **Provider instability (429/5xx).**  
   Mitigation: retries, backoff, degraded-mode logging.
7. **Explainability drift as model complexity increases.**  
   Mitigation: enforce metadata contracts and payload tests per signal type.

---

## 11) Assumptions and Defaults
1. Preserve current ingest/cadence as baseline.
2. Prioritize features that do not require extra provider requests.
3. Keep live/historical/props flags default-off until proven in staging.
4. Keep `signals` as canonical alert-trigger table.
5. Add value via backend APIs + Discord first; no frontend rewrite dependency.
6. CLV/backtesting expansion remains phased and incremental.

---

## 12) Execution Checklist
1. ~~Merge PR1 and verify ingestion parity (no regressions).~~
2. ~~Merge PR2 and verify consensus rows + endpoint responses.~~
3. ~~Merge PR3 and verify dislocation signals + Discord payload quality.~~
4. ~~Merge PR4 and verify low-noise steam behavior in staging.~~
5. ~~Enable live flag in staging only; validate request burn and stability.~~ — SHIPPED. `staging_validation_mode` flag, `/health/flags` endpoint, credit burn logging added. Set `STAGING_VALIDATION_MODE=true` on staging to enable all subsystems.
6. ~~Merge PR6 and validate CLV consistency~~ — SHIPPED.
7. ~~Ship Admin Phase A and B~~ — SHIPPED. Phase A (`previous`), Phase B (`64eee49`, `d3da3b6`).
8. ~~Add KPI alerts~~ — M5 anomaly alerting shipped (`73738c4`). Remaining: live/historical/props production enablement gating.
9. Ship PR7 and complete 7-day staged live-shock burn-rate validation.
10. Ship PR8 and validate partner historical/aggregate API metering under load.
11. Ship PR9 and run Pro digest pilot with delivery/error SLO tracking.
12. Ship PR10 in staging-only mode and approve props cost profile for production rollout.

## Future Surface Area (Not in scope now)
- Historical API v2: bulk exports, materialized-window queries, and cohort-level rollups.
- Aggregate API v2: advanced buckets (venue tier, time bucket, regime, segment joins).
- Partner keys/entitlements lifecycle and overage billing controls (expand from current monetization track).
- Score calibration/normalization by market type (moneyline vs spreads vs totals).
