# Stratum Sports

Institutional-grade NBA betting market intelligence platform.

This is an analytics product, not a picks service and not gambling advice.

## Stack

- Backend: FastAPI, PostgreSQL, Redis, Alembic, async polling worker
- Frontend: Next.js (App Router), TailwindCSS, Recharts
- Auth: JWT (email/password), role/tier gating (`free` vs `pro`)
- Billing: Stripe subscription scaffolding (`$29/mo` configurable)
- Alerts: Discord webhook integration (Pro only)
- Runtime: Docker Compose

## MVP Features Implemented

- Real-time NBA odds ingestion from The Odds API every 60s
- Normalized odds snapshots (`spreads`, `totals`, `h2h`) persisted to Postgres
- Redis-backed dedupe + lightweight poll lock coordination
- Market movement signal engine:
  - `MOVE`
  - `KEY_CROSS`
  - `MULTIBOOK_SYNC`
  - `DISLOCATION` (book vs persisted consensus outlier)
  - `STEAM` (fast synchronized multi-book line moves)
- Free vs Pro enforcement:
  - Free delayed odds (10 minutes)
  - Free watchlist limit of 3
  - Free signal redaction (velocity/components/books hidden)
  - Discord + CSV export blocked for Free
- Pro-only CSV export per event/market
- Discord webhook alert sender with per-user preferences
- Context score scaffolds (`injuries`, `player_props`, `pace`)
- Health endpoints, CORS, rate limiting, structured logs
- Unit tests for signal rules

## Repository Layout

- `backend/` FastAPI app, services, worker, models, alembic migrations, tests
- `frontend/` Next.js App Router UI
- `docker-compose.yml` local stack orchestration
- `.env.example` environment variables template

## Quick Start

1. Optional: copy environment template and set keys.

```bash
cp .env.example .env
```

2. Start everything.

```bash
docker-compose up --build
```

3. Open:
- Frontend: http://localhost:3000
- API: http://localhost:8000/api/v1
- Health: http://localhost:8000/api/v1/health/live

## Production Quick Start

1. Create production env file from template:

```bash
cp .env.production.example .env.production
```

2. Fill all required secrets and production URLs in `.env.production`.
   - PostgreSQL config should use `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`.
   - `DATABASE_URL` is optional advanced override; if blank or contains the placeholder password token, backend/alembic auto-construct it from `POSTGRES_*`.

3. Start production compose stack (pull prebuilt images):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans
```

4. Full deployment runbook:

- `docs/deployment-aws-ec2.md`

### GitHub Actions Production Deploy

Deployment uses two workflows:
- `CI` runs on `push` and `pull_request` and must pass first.
- `Deploy to DigitalOcean` is **manual-only** (`workflow_dispatch`) and verifies CI success for the selected commit before deployment.

The deploy workflow builds images in GitHub and pushes them to GHCR, then the droplet only pulls and restarts containers.
Post-deploy, the workflow validates:
- `/api/v1/health/live`
- `/api/v1/health/ready`

If health checks fail, the workflow prints compose status and service logs before failing.

Required repository secrets:
- `DROPLET_HOST`
- `DROPLET_USER`
- `DROPLET_SSH_KEY`
- `GHCR_USERNAME`
- `GHCR_TOKEN` (token with `read:packages`)

## Frontend API Base URL

Frontend API base URL resolution order:
- `NEXT_PUBLIC_API_BASE_URL`
- `VITE_API_URL`
- `REACT_APP_API_URL`

If none are set:
- Browser in development (`localhost`/`127.0.0.1`) uses `http://localhost:8000/api/v1`
- Production browser uses `window.location.origin + /api/v1`

## Product Guide

- End-user + operator guide: `docs/user-guide.md`
- Release notes / changelog: `CHANGELOG.md`

## Auth Smoke Test

Run against default production target (`http://134.209.125.6:8000`):

```bash
./scripts/smoke_auth.sh
```

Run against a custom target:

```bash
./scripts/smoke_auth.sh http://your-api-host:8000
```

Make target:

```bash
make smoke-auth
```

## Pre-Push Safety Check

Run the lightweight production guardrail checks before pushing:

```bash
make pre-push-check
```

## Admin Bootstrap

Create or update an admin user (idempotent):

```bash
docker compose run --rm backend python -m app.scripts.create_admin --email admin@example.com --password 'replace-with-strong-password'
```

Behavior:
- Sets `is_admin=true`
- Sets `tier=pro`
- Sets `is_active=true`
- Updates password hash
- Rotate password by running the same command with a new `--password` value.

## Deployment Verification Runbook

1) Register test user:

```bash
curl -sS -X POST http://134.209.125.6:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"verify+'$(date +%s)'@example.com","password":"VerifyPass!123"}'
```

2) Login:

```bash
curl -sS -X POST http://134.209.125.6:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}'
```

3) Call protected endpoint with bearer token:

```bash
curl -sS http://134.209.125.6:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

4) Run full smoke test:

```bash
./scripts/smoke_auth.sh http://134.209.125.6:8000
```

Auth failure debug checklist:
- Confirm frontend API base URL is not `localhost` in production.
- Confirm `Authorization: Bearer <token>` header is present on protected requests.
- Confirm backend `CORS_ORIGINS` includes deployed frontend origin.
- Confirm token is valid by calling `/api/v1/auth/me` with curl.
- Confirm deployment uses `docker-compose.prod.yml` and `.env.production`.

## Required Environment Variables for Full Functionality

- `ODDS_API_KEY` (The Odds API)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`

Optional live injury context (SportsDataIO):
- `INJURY_FEED_PROVIDER=heuristic|sportsdataio` (default `heuristic`)
- `SPORTSDATAIO_API_KEY`
- `SPORTSDATAIO_BASE_URL` (default `https://api.sportsdata.io/v3`)
- `SPORTSDATAIO_INJURIES_ENDPOINT_NBA`
- `SPORTSDATAIO_INJURIES_ENDPOINT_NCAAB`
- `SPORTSDATAIO_INJURIES_ENDPOINT_NFL`

Notes:
- Endpoints are plan-specific at SportsDataIO. Leave endpoint vars blank to keep heuristic fallback behavior.
- If live feed is unavailable for any reason, context scoring automatically falls back to spread-velocity heuristics.

## Discord OAuth Setup

1. Create an application at [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy the **Client ID** and **Client Secret** to your `.env` file.
3. Go to the **OAuth2** -> **General** tab in the Discord Portal.
4. Add a **Redirect URI**: `http://localhost:3000/auth/discord/callback`.
5. Click **Save Changes**.

Without these, the app runs but external ingestion/billing/social login flows are limited.

## API Pull Budget Controls

If you are running low on The Odds API credits, tune these:

- `ODDS_POLL_INTERVAL_SECONDS` (default `60`): active cadence when events are available
- `ODDS_POLL_INTERVAL_IDLE_SECONDS` (default `300`): cadence when no events are returned
- `ODDS_POLL_INTERVAL_LOW_CREDIT_SECONDS` (default `900`): cadence when credits are low
- `ODDS_API_LOW_CREDIT_THRESHOLD` (default `200`): triggers low-credit cadence at or below this value
- `ODDS_API_TARGET_DAILY_CREDITS` (default `1200`): budget guardrail; poller stretches interval to stay near this burn rate
- `ODDS_API_SPORT_KEYS` (default `basketball_nba,basketball_ncaab,americanfootball_nfl`): comma-separated sports polled each cycle
- `ODDS_API_BOOKMAKERS` (optional): comma-separated bookmaker keys to reduce request cost

The poller reads response headers (`x-requests-remaining`, `x-requests-used`, `x-requests-last`) and automatically slows down in low-credit mode.
It also applies a daily budget interval floor using `x-requests-last`:

`min_interval_seconds = ceil((x_requests_last * 86400) / ODDS_API_TARGET_DAILY_CREDITS)`

## Close Capture Mode (Live Polling)

Close capture mode boosts cadence near tipoff while reducing far-from-tip polling to improve close-line quality with bounded request growth.

Cadence bands per event:
- `minutes_to_tip > 180`: 15m cadence (or slower if base cadence is slower)
- `180 >= minutes_to_tip > 60`: 5m cadence
- `60 >= minutes_to_tip > -15`: 60s cadence
- `minutes_to_tip <= -15`: event polling stops

Environment controls:
- `STRATUM_CLOSE_CAPTURE_ENABLED` (default `true`)
- `STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE` (default `10`)

Quota safety:
- poller tracks per-event `next_poll_at` in memory and only ingests due events
- hard cap on due events per cycle via `STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE`
- existing low-credit and budget header checks remain active

## One-Off Historical Backfill (NBA)

Use this one-off tool to backfill recent historical odds snapshots into `games` and `odds_snapshots` for charts/backtests.

Historical endpoint strategy (The Odds API v4):
- Preferred: `GET /v4/historical/sports/{sport_key}/odds?date=...`
- Fallback: `GET /v4/historical/sports/{sport_key}/events/{event_id}/odds?date=...`
- The tool uses `date` (ISO8601 `Z`) for historical snapshots and reads `x-requests-*` headers for budget control.

Probe only (no writes) to verify endpoint support before running a full backfill:

```bash
docker compose run --rm --no-deps backend \
  python -m app.tools.backfill_history \
  --probe_only true \
  --start 2026-02-18T00:00:00Z \
  --end 2026-02-22T00:00:00Z \
  --sport_key basketball_nba \
  --markets spreads,totals \
  --max_events 1 \
  --max_requests 5
```

Command:

```bash
docker compose run --rm --no-deps backend \
  python -m app.tools.backfill_history \
  --start 2026-02-18T00:00:00Z \
  --end 2026-02-22T00:00:00Z \
  --sport_key basketball_nba \
  --markets spreads,totals,h2h \
  --max_events 10 \
  --max_requests 200 \
  --min_requests_remaining 50
```

Safety behaviors:
- Hard budget stop when `max_requests` is reached.
- Hard budget stop when remaining credits drop to `min_requests_remaining`.
- Idempotent DB-side dedupe on exact snapshot key `(event, book, market, outcome, line, price, fetched_at)`.
- Logs and prints summary with requests used, snapshots inserted, duplicates skipped, and timestamp coverage.

Warning:
- This is intentionally credit-sensitive. Start with small windows and low `--max_events` / `--max_requests`.

## Recommended First Real Dataset Backfill (NBA)

Run this larger first pass to seed enough history for CLV close diagnostics and backtests:

```bash
docker compose run --rm --no-deps backend python -m app.tools.backfill_history \
  --start 2026-02-20T00:00:00Z \
  --end   2026-02-23T00:00:00Z \
  --sport_key basketball_nba \
  --markets spreads,totals,h2h \
  --max_events 50 \
  --max_requests 1200 \
  --min_requests_remaining 150 \
  --history_step_minutes 120
```

After the run:

```bash
docker compose run --rm --no-deps backend python -m app.tools.dataset_sanity
```

Expected outcomes:
- Multiple events covered in `odds_snapshots`
- Multi-book distribution across major books
- At least some events flagged as `close_covered` in close coverage diagnostics

Dataset build runner (backfill + sanity in one command):

```bash
python -m app.tools.run_dataset_build
```

Example with overrides:

```bash
python -m app.tools.run_dataset_build --history_step_minutes 60
```

Live Data Snapshot:

```bash
docker compose run --rm backend python -m app.tools.print_live_data_snapshot
```

Actionable Live Board:

```bash
docker compose run --rm backend python -m app.tools.print_actionable_live_board
```

## Research Backfill (Completed Games)

Use this runner for Path B research windows that are fully in the past (completed games), then review close coverage quality before CLV evaluation.

```bash
python -m app.tools.run_research_backfill
```

Do not use future windows for CLV evaluation; close-line diagnostics and signal grading require completed games.

## Fix Close Capture (One Command)

```bash
docker compose run --rm ops sh -lc "apk add --no-cache docker-cli docker-cli-compose python3 && PYTHONPATH=/work/backend python3 -m app.tools.fix_close_capture"
```

## Consensus Snapshot Controls

Consensus snapshots are computed from stored `odds_snapshots` after each ingestion commit. This does not create extra external API calls.

- `CONSENSUS_ENABLED` (default `true`)
- `CONSENSUS_LOOKBACK_MINUTES` (default `10`)
- `CONSENSUS_MIN_BOOKS` (default `5`)
- `CONSENSUS_MARKETS` (default `spreads,totals,h2h`)
- `CONSENSUS_RETENTION_DAYS` (default `14`)

## Odds API Resilience Controls

Live odds polling includes bounded retry/backoff and a temporary circuit-open guard to avoid hard poller failures during upstream instability.

- `ODDS_API_RETRY_ATTEMPTS` (default `3`)
- `ODDS_API_RETRY_BACKOFF_SECONDS` (default `1.0`)
- `ODDS_API_RETRY_BACKOFF_MAX_SECONDS` (default `8.0`)
- `ODDS_API_CIRCUIT_FAILURES_TO_OPEN` (default `3`)
- `ODDS_API_CIRCUIT_OPEN_SECONDS` (default `120`)

## Dislocation Signal Controls

Dislocation detection runs in the existing signal pipeline and compares latest per-book odds snapshots to persisted consensus snapshots (no extra external API calls).

- `DISLOCATION_ENABLED` (default `true`)
- `DISLOCATION_LOOKBACK_MINUTES` (default `10`)
- `DISLOCATION_MIN_BOOKS` (default `5`)
- `DISLOCATION_SPREAD_LINE_DELTA` (default `1.0`)
- `DISLOCATION_TOTAL_LINE_DELTA` (default `2.0`)
- `DISLOCATION_ML_IMPLIED_PROB_DELTA` (default `0.03`)
- `DISLOCATION_COOLDOWN_SECONDS` (default `900`)
- `DISLOCATION_MAX_SIGNALS_PER_EVENT` (default `6`)

## Steam v2 Signal Controls

Steam v2 detects fast, same-direction line movement across multiple books using only `odds_snapshots`. No extra external API calls are made.

- `STEAM_ENABLED` (default `true`)
- `STEAM_WINDOW_MINUTES` (default `3`)
- `STEAM_MIN_BOOKS` (default `4`)
- `STEAM_MIN_MOVE_SPREAD` (default `0.5`)
- `STEAM_MIN_MOVE_TOTAL` (default `1.0`)
- `STEAM_COOLDOWN_SECONDS` (default `900`)
- `STEAM_MAX_SIGNALS_PER_EVENT` (default `4`)
- `STEAM_DISCORD_ENABLED` (default `false`, shadow mode)

## CLV Tracking Controls

CLV tracking is computed from existing `games.commence_time`, persisted `market_consensus_snapshots`, and persisted `signals`. No additional external API calls are made.

- `CLV_ENABLED` (default `true`)
- `CLV_MINUTES_AFTER_COMMENCE` (default `10`)
- `CLV_LOOKBACK_DAYS` (default `7`)
- `CLV_RETENTION_DAYS` (default `60`)
- `CLV_JOB_INTERVAL_MINUTES` (default `60`)

## Performance Intel Controls

Performance intel powers `/app/performance` and actionable signal cards in `/app/games/[event_id]`.
The performance page includes Pro-only 1-click signal quality presets (`High Confidence`, `Low Noise`, `Early Move`, `Steam Only`) persisted locally in browser storage and executed via server-side filters.

- `PERFORMANCE_UI_ENABLED` (default `true`)
- `ACTIONABLE_BOOK_CARD_ENABLED` (default `true`)
- `PERFORMANCE_DEFAULT_DAYS` (default `30`)
- `PERFORMANCE_MAX_LIMIT` (default `200`)
- `SIGNAL_FILTER_DEFAULT_MIN_STRENGTH` (default `60`)
- `ACTIONABLE_BOOK_MAX_BOOKS` (default `8`)
- `FREE_TEASER_ENABLED` (default `true`)

## Cycle KPI Controls

Cycle KPIs persist one operational summary row per poller cycle for internal observability (burn, throughput, signals, alerts, latency) using existing in-process data only.

- `KPI_ENABLED` (default `true`)
- `KPI_RETENTION_DAYS` (default `30`)
- `KPI_WRITE_FAILURES_SOFT` (default `true`)
- `OPS_INTERNAL_TOKEN` (required in production; sent via `X-Stratum-Ops-Token` for `/api/v1/ops/*`)

## Ops Digest Controls

Internal weekly digest posts the operator report to an internal Discord webhook. It is deduped per ISO week and skipped when webhook is not configured.

- `OPS_DIGEST_ENABLED` (default `false`)
- `OPS_DIGEST_WEBHOOK_URL` (default empty)
- `OPS_DIGEST_WEEKDAY` (default `1`, Monday)
- `OPS_DIGEST_HOUR_UTC` (default `13`)
- `OPS_DIGEST_MINUTE_UTC` (default `0`)
- `OPS_DIGEST_LOOKBACK_DAYS` (default `7`)

## Core API Routes

- Auth: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/me`
- Auth Password Reset: `/api/v1/auth/password-reset/request`, `/api/v1/auth/password-reset/confirm`
- Dashboard: `/api/v1/dashboard/cards`
- Games: `/api/v1/games`, `/api/v1/games/{event_id}`
- Intel (Pro): `/api/v1/intel/consensus?event_id=...&market=spreads|totals|h2h`, `/api/v1/intel/consensus/latest?event_id=...`
- Intel CLV (Pro): `/api/v1/intel/clv?days=30&event_id=...&signal_type=...&market=...&min_strength=...&limit=...`, `/api/v1/intel/clv/summary?days=30&signal_type=...&market=...&min_samples=...&min_strength=...`, `/api/v1/intel/clv/scorecards?days=30&signal_type=...&market=...&min_samples=...&min_strength=...`
- Intel Signal Quality (Pro): `/api/v1/intel/signals/quality?days=30&signal_type=...&market=...&min_strength=...`
- Intel Actionable Books (Pro): `/api/v1/intel/books/actionable?event_id=...&signal_id=...`, `/api/v1/intel/books/actionable/batch?event_id=...&signal_ids=<uuid,uuid,...>`
- Intel CLV Teaser (Authenticated Free/Pro): `/api/v1/intel/clv/teaser?days=30`
- Ops KPIs (Internal token): `/api/v1/ops/cycles?days=7&limit=200`, `/api/v1/ops/cycles/summary?days=7`, `/api/v1/ops/report?days=7`
- Pro CSV export: `/api/v1/games/{event_id}/export.csv?market=spreads|totals|h2h`
- Watchlist: `/api/v1/watchlist`
- Discord (Pro): `/api/v1/discord/connection`
- Billing: `/api/v1/billing/create-checkout-session`, `/api/v1/billing/portal`, `/api/v1/billing/webhook`

Discord webhook URLs must match the configured allowlist (`DISCORD_WEBHOOK_ALLOWED_HOSTS`, default `discord.com,ptb.discord.com,canary.discord.com`) and the `/api/webhooks/...` path.

## Migrations

Migrations auto-run in backend and worker startup (`alembic upgrade head`).

Manual run:

```bash
docker-compose run --rm backend alembic upgrade head
```

## Tests

```bash
docker-compose --env-file .env.example run --rm --no-deps backend pytest -q
```

## Notes

- Polling worker runs as separate container (`worker`) and executes every 60 seconds.
- Free-tier delayed enforcement happens in backend query layer; UI hiding is not the only control.
- Local Postgres is mapped to host port `5433` by default (`POSTGRES_HOST_PORT`) to avoid common `5432` conflicts.
- Password reset request returns a generic response in all environments. In non-production, a temporary `reset_token` is included to support local/dev testing.
