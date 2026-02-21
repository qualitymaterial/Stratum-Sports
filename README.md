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

## Required Environment Variables for Full Functionality

- `ODDS_API_KEY` (The Odds API)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`

Without these, the app runs but external ingestion/billing flows are limited.

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
- If port `5432` is already occupied locally, adjust DB host port mapping in `docker-compose.yml`.
