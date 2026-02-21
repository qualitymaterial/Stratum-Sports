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

3. Start production compose stack:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

4. Full deployment runbook:

- `docs/deployment-aws-ec2.md`

## Product Guide

- End-user + operator guide: `docs/user-guide.md`
- Release notes / changelog: `CHANGELOG.md`

## Required Environment Variables for Full Functionality

- `ODDS_API_KEY` (The Odds API)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`

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
- `ODDS_API_BOOKMAKERS` (optional): comma-separated bookmaker keys to reduce request cost

The poller reads response headers (`x-requests-remaining`, `x-requests-used`, `x-requests-last`) and automatically slows down in low-credit mode.
It also applies a daily budget interval floor using `x-requests-last`:

`min_interval_seconds = ceil((x_requests_last * 86400) / ODDS_API_TARGET_DAILY_CREDITS)`

## Core API Routes

- Auth: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/me`
- Dashboard: `/api/v1/dashboard/cards`
- Games: `/api/v1/games`, `/api/v1/games/{event_id}`
- Pro CSV export: `/api/v1/games/{event_id}/export.csv?market=spreads|totals|h2h`
- Watchlist: `/api/v1/watchlist`
- Discord (Pro): `/api/v1/discord/connection`
- Billing: `/api/v1/billing/create-checkout-session`, `/api/v1/billing/portal`, `/api/v1/billing/webhook`

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
