# Stratum Sports Plan

## 1) Executive Summary
Stratum has pivoted from a premium betting product to a **Market Intelligence Infrastructure Layer**. 

The core system now supports real-time signal distribution via a high-performance **Webhook Delivery Engine**, institutional-grade usage metering, and the "Infrastructure" pricing tier.

The highest-leverage path forward is:
1. Signal delivery scaling (Webhooks v1 shipped).
2. Institutional analytics (Book dislocation and Steam v2).
3. Strategic pricing ($149/mo base for Infrastructure partners).
4. Sales-driven usage anomaly alerting.

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
| Signal engine | Movement detection, key-cross, multibook sync, strength scoring | `backend/app/services/signals.py` (`detect_market_movements`, `compute_strength_score`) |
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
2. Poller calls `ingest_odds_cycle` in `backend/app/services/ingestion.py`.
3. Ingestion calls `OddsApiClient.fetch_nba_odds` in `backend/app/services/odds_api.py`.
4. Payload normalizes into `OddsSnapshot` rows and `Game` upserts.
5. Redis dedupe key prevents duplicate snapshot inserts: `odds:last:{event}:{book}:{market}:{outcome}`.
6. Each inserted snapshot emits Pub/Sub `odds_updates` for realtime stream.
7. Poller passes updated `event_ids` to `detect_market_movements`.
8. Signal engine computes `MOVE`, `KEY_CROSS`, `MULTIBOOK_SYNC`, and commits `Signal` rows.
9. Poller dispatches Discord alerts for Pro watchlist users.
10. Periodic retention cleanup runs for old snapshots/signals.
11. Adaptive interval logic responds to provider request-budget headers.

### 2.3 Current Signal Rules and Alert Context
- Spread trigger: abs move `>= 0.5` or key-number cross (`NBA_KEY_NUMBERS`).
- Total trigger: abs move `>= 1.0`.
- Multibook trigger: `>= 3` books same direction in 5-minute window.
- Strength score: magnitude + speed + books, clamped to 1..100.
- Discord controls: `min_strength`, `alert_spreads`, `alert_totals`, `alert_multibook`.
- Context score exists but is currently scaffolded (`injuries`, `props`, `pace` proxies).

### 2.4 Persistence and State
**Postgres tables (core):**
- `games`
- `odds_snapshots`
- `signals`
- `watchlists`
- `discord_connections`
- `users`
- `subscriptions`

**Redis keys/channels (core):**
- `poller:odds-ingest-lock`
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
  - Book/region/market filters
  - `FREE_DELAY_MINUTES`
  - `FREE_WATCHLIST_LIMIT`

---

## 3) Maturity Snapshot

### 3.1 Capability Matrix
| Capability | Maturity (0-3) | Robustness notes | Gaps |
|---|---:|---|---|
| Data ingest (pregame odds) | 2 | Async poller, dedupe, upsert, retention cleanup | Single endpoint path only; no modular endpoint selection |
| Normalization | 2 | Stable schema for h2h/spreads/totals | No generalized normalizer for props/historical/live variants |
| Scoring/signals | 2 | Clear rules + metadata + unit tests | Missing dislocation/steam-v2/live-shock/CLV signals |
| Alert routing | 2 | Pro-only, per-user prefs, min-strength, Discord delivery | No batching/digest, no retry queue, no delivery metrics table |
| Persistence | 2 | Indexed snapshots/signals and normalized games | No consensus snapshot table, no props table, no closing-line table |
| Scheduling/job coordination | 2 | Redis lock + adaptive intervals + cleanup cadence | Single-loop architecture for all tasks |
| Monitoring/ops | 1 | Health endpoints, structured logs, optional Sentry | No robust metrics/SLO dashboard |
| Docs/runbooks | 2 | README + deploy runbook + user guide | Missing full roadmap spec in one clean execution flow |
| Testing | 1 | Signal/auth/watchlist/billing/poller tests exist | No broad end-to-end cycle test harness |
| Backtesting/research | 0-1 | Partial utility work | No full signal-efficacy lifecycle loop |

### 3.2 Top Strengths
1. Strong ingestion-to-alert operational loop.
2. Efficient DB query patterns for dashboard and signal paths.
3. Cost-aware polling tied to real provider usage headers.
4. Backend-enforced tier gating.
5. Good modular boundaries across fetch/ingest/signal/alert/API layers.

### 3.3 Top Gaps
1. No persisted consensus/dislocation layer.
2. No bounded watchlist live-shock path.
3. No full close/CLV analytics loop.
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
| 1 | Book dislocation scanner + dislocation score | 5 | 5 | 5 | 5 | 4 | 24 | Tier 1 |
| 2 | Steam detection v2 (velocity + tighter book sync) | 5 | 5 | 5 | 4 | 4 | 23 | Tier 1 |
| 3 | Persisted consensus/dispersion snapshots | 4 | 5 | 4 | 5 | 4 | 22 | Tier 1 |
| 4 | Watchlist-scoped live shock alerts | 5 | 3 | 3 | 4 | 4 | 19 | Tier 2 |
| 5 | Historical close ingestion + CLV tracker | 4 | 3 | 3 | 5 | 4 | 19 | Tier 2 |
| 6 | Player props ingestion foundation | 4 | 3 | 2 | 4 | 5 | 18 | Tier 2 |
| 7 | Player props mispricing radar | 5 | 2 | 2 | 3 | 5 | 17 | Tier 3 |

### 4.3 Candidate Scoping (Condensed)
1. **Dislocation scanner**
   - Value: outlier book detection vs consensus for actionable intel.
   - Effort: 4-6 days.
   - Cost impact: near-zero incremental if computed from existing snapshots.
   - Fit: extends current signal loop.
2. **Steam v2**
   - Value: captures coordinated, rapid market shifts.
   - Effort: 3-5 days.
   - Cost impact: none incremental.
3. **Consensus persistence**
   - Value: stable analytics substrate for dislocation/steam explainability.
   - Effort: 4-6 days.
   - Cost impact: none incremental.
4. **Live shock alerts**
   - Value: high-value real-time alerting on watchlist events.
   - Effort: 1-2 weeks.
   - Cost impact: medium-high without strict budget controls.
5. **Historical close + CLV**
   - Value: quantifies edge and product credibility.
   - Effort: 1-2 weeks.
   - Cost impact: low daily after backfill.
6. **Props foundation**
   - Value: unlocks next monetization surface.
   - Effort: 1-2 weeks foundation only.
   - Cost impact: high unless tightly scoped.
7. **Props mispricing radar**
   - Value: high but model-dependent.
   - Effort: >2 weeks and additional data dependencies.
   - Cost impact: medium-high.

---

## 5) Roadmap (Now / Next / Later)

### 5.1 Now (0-3 weeks)
1. Consensus/dispersion persistence.
2. Dislocation signal type + Discord formatting.
3. Steam detection v2 using current snapshots.
4. Minimal intel API endpoints for machine-readable packaging.

### 5.2 Next (3-6 weeks)
1. Watchlist-scoped live shock alerts with hard budget controls.
2. Historical close ingestion and CLV computations.
3. Optional Pro digest summaries (daily/weekly).

### 5.3 Later (6+ weeks)
1. Player props ingestion foundation (narrow scope first).
2. Props mispricing radar once projection inputs are available.
3. Cross-sport generalization after NBA stability is proven.

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
1. **API Monthly Plan**
   - Base price: `$99/month` (current public positioning).
   - Includes a monthly usage allowance (set in Stripe meter config).
2. **API Annual Plan**
   - Annual prepay version of API access.
   - Includes annual usage allowance and overage billing.
3. **Overage**
   - Metered billing above included allowance.
   - Charged per usage unit (e.g., per 1,000 API calls) on monthly invoice.
4. **Plan boundaries**
   - Web Pro and API Partner remain distinct entitlements and separate billing products.
   - Accounts can hold one or both products.

### 6.3 Entitlements and Access Control
1. Add explicit API entitlement state per account:
   - `api_access_enabled`
   - `api_plan_code` (`api_monthly`, `api_annual`)
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
6. ~~Merge PR5 and validate CLV consistency~~ — SHIPPED (`b8c2ba5`).
7. ~~Ship Admin Phase A and B~~ — SHIPPED. Phase A (`previous`), Phase B (`64eee49`, `d3da3b6`).
8. ~~Add KPI alerts~~ — M5 anomaly alerting shipped (`73738c4`). Remaining: live/historical/props production enablement gating.

## Future Surface Area (Not in scope now)
- Historical API access with explicit date-range query support.
- Aggregate endpoints (daily performance, bucket summaries, cohort-level rollups).
- Partner keys/entitlements lifecycle and overage billing controls (expand from current monetization track).
- Score calibration/normalization by market type (moneyline vs spreads vs totals).
