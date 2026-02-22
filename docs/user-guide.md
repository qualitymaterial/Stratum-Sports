# Stratum Sports User Guide

Stratum Sports is an analytics platform for NBA betting market intelligence. It is not a picks service and not gambling advice.

## 1. Before You Start

### Prerequisites

- Docker Desktop running
- A valid The Odds API key
- Optional for full functionality: Stripe keys and Discord OAuth credentials

### Required Environment Setup

1. Copy the template:

```bash
cp .env.example .env
```

2. Set at minimum:

- `ODDS_API_KEY`
- `NEXT_PUBLIC_API_BASE_URL` (local default is already set)
- `JWT_SECRET` (required for production)

3. Optional but recommended for budget control:

- `ODDS_API_TARGET_DAILY_CREDITS`
- `ODDS_API_BOOKMAKERS`

## 2. Start The Platform

```bash
docker compose up --build
```

Open:

- Web app: `http://localhost:3000`
- API root: `http://localhost:8000/api/v1`
- Live health: `http://localhost:8000/api/v1/health/live`
- Ready health: `http://localhost:8000/api/v1/health/ready`

If `localhost:3000` does not load, confirm containers are up:

```bash
docker ps
```

## 3. First Login Flow

1. Go to `http://localhost:3000/register`.
2. Create an account (email/password).
3. You are redirected to `/app/dashboard`.
4. Use `/login` on future sessions.
5. Optional: use Discord OAuth from the login page if Discord credentials are configured.

## 4. App Navigation

### Dashboard (`/app/dashboard`)

Use this as your command center:

- Game cards with matchup + start time
- Consensus spread, total, and moneyline
  - Spread is displayed as the home-team consensus spread (same convention as game detail chart).
- Mini movement sparkline
- Recent signal badges
- Live stream status indicator for Pro users

### Game Detail (`/app/games/[event_id]`)

Use this for deeper analysis:

- Full odds table by sportsbook
- Movement chart over time
- Chronological signals
- Context framework output (`injuries`, `player_props`, `pace`)
- CSV export buttons (Pro only)

### Watchlist (`/app/watchlist`)

Use this to track focus games:

- Add/remove games
- Open tracked game detail quickly
- Free tier: up to 3 games
- Pro tier: unlimited

### Alerts (`/app/discord`)

Pro-only alert management:

- Save Discord webhook URL
- Toggle spreads/totals/multibook alerts
- Set minimum strength threshold
- Enable/disable alert delivery

### Billing (header actions)

- Free users: `Upgrade` opens Stripe checkout
- Pro users: `Billing` opens Stripe portal

## 5. Free vs Pro Behavior

### Free Tier

- Odds delayed by 10 minutes (enforced server-side)
- Watchlist capped at 3 games
- Discord alerts unavailable
- Signal metadata is redacted (no velocity/books/components)
- CSV export unavailable

### Pro Tier

- Real-time odds access
- Full signal diagnostics and history
- Unlimited watchlist
- Discord alerts enabled
- CSV export enabled

## 6. Operator Guide (Running It Reliably)

### Monitor Worker Health

```bash
docker compose logs -f worker
```

Look for:

- `Starting odds poller`
- `Odds ingestion cycle completed`
- `Adaptive polling interval applied`

### Monitor API Budget Usage

Worker logs include:

- `requests_remaining`
- `requests_used`
- `requests_last`

If credits are burning too quickly, adjust `.env`:

- Increase `ODDS_POLL_INTERVAL_SECONDS`
- Increase `ODDS_POLL_INTERVAL_IDLE_SECONDS`
- Increase `ODDS_POLL_INTERVAL_LOW_CREDIT_SECONDS`
- Lower `ODDS_API_TARGET_DAILY_CREDITS`
- Reduce market/book scope with `ODDS_API_MARKETS` and `ODDS_API_BOOKMAKERS`

Then reload worker:

```bash
docker compose up -d --force-recreate worker
```

### Validate External Integrations

- Stripe: test `create-checkout-session` and webhook handling
- Discord: save webhook and force a low-threshold alert config
- Odds API: confirm non-empty events and snapshots in dashboard/game detail

## 7. Pre-Launch Smoke Test Checklist

1. Register and login with email/password.
2. Confirm dashboard loads upcoming games.
3. Open a game detail page and verify odds + chart render.
4. Add and remove a game from watchlist.
5. Verify Free watchlist limit is enforced at 3 games.
6. Verify Free users cannot access Discord alerts.
7. Verify Free users cannot export CSV.
8. Upgrade to Pro test account.
9. Verify Discord settings save for Pro.
10. Verify CSV export works for Pro.
11. Verify live websocket status connects for Pro.
12. Confirm `/api/v1/health/live` and `/api/v1/health/ready` return expected status.

## 8. Troubleshooting

### Docker daemon error

If you see `Cannot connect to the Docker daemon`, start Docker Desktop first.

### Port conflicts

Default mappings:

- Frontend: `3000`
- Backend: `8000`
- Redis: `6379`
- Postgres host port: `5433` (container still uses `5432`)

Use `POSTGRES_HOST_PORT` in `.env` if needed.

### Dashboard empty

Check:

- `ODDS_API_KEY` is valid
- `worker` container is running
- worker logs show successful odds responses

### Discord login fails

Check:

- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_REDIRECT_URI` matches Discord app settings exactly

### Stripe actions fail

Check:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRO_PRICE_ID`

## 9. Glossary

- `American Odds`: Odds format like `-110` or `+135`.
- `Consensus Line`: Average market value across tracked sportsbooks.
- `Context Score`: Supplemental framework output (`injuries`, `player_props`, `pace`) to aid interpretation.
- `Event`: A game instance from provider data, identified by `event_id`.
- `Fetched At`: Timestamp when snapshot was ingested.
- `H2H`: Head-to-head moneyline market.
- `Key Number`: Important spread levels monitored for crossings (configured in `NBA_KEY_NUMBERS`).
- `Market`: Odds category such as `spreads`, `totals`, or `h2h`.
- `MOVE`: Signal indicating meaningful line change within a time window.
- `MULTIBOOK_SYNC`: Signal indicating 3+ books moved same direction in a short window.
- `Odds Snapshot`: Normalized row storing one book/outcome/market value at a point in time.
- `Poll Cycle`: One worker execution that fetches odds and processes signals.
- `Price`: American odds value for an outcome.
- `Pro Gating`: Backend enforcement that locks premium features to Pro tier users.
- `Signal`: Persisted market movement event with score, direction, and metadata.
- `Spread`: Point handicap market.
- `Strength Score`: 1-100 heuristic using move magnitude, speed, and books affected.
- `Total`: Combined points market (`Over`/`Under`).
- `Velocity`: Time in minutes between start and end of detected move window.
- `Watchlist`: User-managed set of events to track and alert on.
