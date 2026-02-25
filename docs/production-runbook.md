# Stratum Production Runbook (DigitalOcean + GitHub Actions)

This is the primary runbook for deploying, verifying, and rolling back Stratum in production.

Safety policy (locked):

- Deploys are manual only (`workflow_dispatch`).
- CI runs automatically but never deploys by itself.
- Stripe sandbox tests run locally first before any production deploy.

## Command Context Legend

- `[Mac]` run in your local Mac terminal (`briananderson@Mac ...`)
- `[Droplet]` run on the server shell (`root@...`)
- `[GitHub UI]` run in the GitHub web interface

If you are at a `root@...` prompt, do not run `pbcopy` or Mac key commands there.

## 0) Context-Safe Command Packs

Use only one context per block. Do not mix `[Mac]` and `[Droplet]` commands in the same paste.

### 0.1 Quick health checks from Mac

```bash
# [Mac]
make prod-smoke
```

Optionally override host:

```bash
# [Mac]
PROD_HOST=104.236.237.83 make prod-smoke
```

### 0.2 Quick container checks on droplet

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready
```

## 1) One-Time Setup

### 1.1 Verify deploy SSH key pair

1. `[Mac]` confirm local key exists:

```bash
ls -l ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

2. `[Droplet]` ensure matching public key exists:

```bash
grep -n "stratum" /root/.ssh/authorized_keys
```

### 1.2 Configure GitHub Actions secrets

`[GitHub UI]` Repo -> Settings -> Secrets and variables -> Actions

Required secrets:

- `DROPLET_HOST` (example: `104.236.237.83`)
- `DROPLET_USER` (`root`)
- `DROPLET_SSH_KEY` (full private key block from `~/.ssh/id_ed25519`)
- `GHCR_USERNAME` (`qualitymaterial`)
- `GHCR_TOKEN` (PAT with at least `read:packages`)

To copy SSH private key safely:

```bash
# [Mac]
pbcopy < ~/.ssh/id_ed25519
```

### 1.3 Lock down `main` branch

`[GitHub UI]` Repo -> Settings -> Branches -> Add rule for `main`:

- Require a pull request before merging
- Require at least 1 approval
- Require status checks to pass (select CI workflow)
- Restrict direct pushes to `main`

This is mandatory for maximum-safety mode.

### 1.4 Ensure production env file exists

```bash
# [Droplet]
cd /opt/stratum-sports
test -f .env.production || cp .env.production.example .env.production
```

Minimum required keys for stable startup:

- `APP_ENV=production`
- `JWT_SECRET` (strong, non-placeholder)
- `OPS_INTERNAL_TOKEN` (strong, non-placeholder)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `DATABASE_URL` (recommended explicit value)
- `REDIS_URL`

Recommended for full functionality:

- `ODDS_API_KEY`
- Stripe keys: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`
- Optional: `SPORTSDATAIO_API_KEY`

## 2) Environment Isolation Rules

1. Local runtime uses only `.env` with `docker-compose.yml`.
2. Production runtime uses only `.env.production` with `docker-compose.prod.yml`.
3. Never copy `.env` to the droplet.
4. Never reuse `.env.production` locally.
5. Stripe keys:
   - local: `STRIPE_SECRET_KEY=sk_test_*`
   - production: `STRIPE_SECRET_KEY=sk_live_*`

## 3) Stripe Sandbox Test Lane (Local First)

Run this before any production deploy.

### 3.1 Start local stack

```bash
# [Mac]
cd "/Users/briananderson/Documents/Prototypes/Stratum Sports"
docker compose up -d --build
docker compose ps
```

### 3.2 Forward Stripe webhooks to local backend

```bash
# [Mac]
stripe login
stripe listen --forward-to localhost:8000/api/v1/billing/webhook
```

### 3.3 Validate billing flow

1. Checkout opens from `Upgrade`.
2. Webhook is processed (`Stripe webhook processed` in backend logs).
3. User tier transitions `free -> pro`.
4. Billing portal opens for Pro user.
5. Subscription cancellation transitions `pro -> free`.

Only after these pass should you deploy to production.

## 4) Standard Deploy (Manual-Only)

### 4.1 Trigger deploy workflow

`[GitHub UI]` Actions -> **Deploy to DigitalOcean** -> **Run workflow** on `main`.

Deploy workflow is manual-only by design. CI completion does not deploy.

The workflow performs:

- CI verification for target SHA
- backend/frontend image build + push to GHCR
- SSH deploy on droplet
- backend health checks (`/health/live` + `/health/ready`)

### 4.2 Verify deployment

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/live
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready
```

```bash
# [Mac]
curl -I --max-time 10 http://<DROPLET_IP>:3000
```

## 5) Release Lane (Promotion Flow)

1. Develop only on a feature branch.
2. Open PR to `main`.
3. Merge only after CI is green and reviewed.
4. Trigger manual deploy from GitHub Actions.
5. Run post-deploy smoke checks:
   - backend health `live` + `ready`
   - login works
   - dashboard loads
   - billing button opens expected flow
   - worker stable for 10-15 minutes

## 6) Emergency Manual Deploy by SHA

Use this only if GitHub Actions is unavailable or delayed.

```bash
# [Droplet]
cd /opt/stratum-sports
git fetch origin main
git checkout main
git pull --ff-only origin main

SHA=<commit_sha>

# wait until both images exist in GHCR
until docker manifest inspect ghcr.io/qualitymaterial/stratum-sports-backend:$SHA >/dev/null 2>&1 \
  && docker manifest inspect ghcr.io/qualitymaterial/stratum-sports-frontend:$SHA >/dev/null 2>&1; do
  echo "Waiting for GHCR images for $SHA ..."
  sleep 20
done

docker pull ghcr.io/qualitymaterial/stratum-sports-backend:$SHA
docker pull ghcr.io/qualitymaterial/stratum-sports-frontend:$SHA

BACKEND_IMAGE=ghcr.io/qualitymaterial/stratum-sports-backend:$SHA \
WORKER_IMAGE=ghcr.io/qualitymaterial/stratum-sports-backend:$SHA \
FRONTEND_IMAGE=ghcr.io/qualitymaterial/stratum-sports-frontend:$SHA \
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans
```

## 7) Rollback (Fast, Reversible)

1. Find previous known-good image SHA.
2. Keep a running release log (deploy issue or release notes) of each known-good SHA.
3. Redeploy with that SHA:

```bash
# [Droplet]
GOOD_SHA=<known_good_sha>
docker pull ghcr.io/qualitymaterial/stratum-sports-backend:$GOOD_SHA
docker pull ghcr.io/qualitymaterial/stratum-sports-frontend:$GOOD_SHA

BACKEND_IMAGE=ghcr.io/qualitymaterial/stratum-sports-backend:$GOOD_SHA \
WORKER_IMAGE=ghcr.io/qualitymaterial/stratum-sports-backend:$GOOD_SHA \
FRONTEND_IMAGE=ghcr.io/qualitymaterial/stratum-sports-frontend:$GOOD_SHA \
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans
```

4. Re-run health checks from section 4.2.

## 8) Credential and Access Controls

1. `GHCR_TOKEN` on droplet should remain minimal scope (`read:packages`).
2. Rotate deploy SSH key and GHCR PAT on a regular schedule.
3. Keep Stripe live keys only in:
   - GitHub Actions secrets
   - droplet `.env.production`
4. Never store live keys in repo files, commits, or chat logs.

## 9) Env Sync and Safe Restart

When changing `.env.production`:

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready
```

If frontend-only env changed (for example `NEXT_PUBLIC_*`), recreate frontend:

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --force-recreate frontend
```

## 10) Quick Diagnostics

### 10.1 Backend restarting

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 backend
```

Common causes:

- DB auth mismatch (`InvalidPasswordError`)
- placeholder secrets in production (`JWT_SECRET`, `OPS_INTERNAL_TOKEN`)
- invalid/missing env values

### 10.2 App login fails with 500

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 backend
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready
```

### 10.3 GitHub deploy fails with SSH/auth errors

Check:

- `DROPLET_HOST`, `DROPLET_USER`, `DROPLET_SSH_KEY` secrets
- matching public key in `/root/.ssh/authorized_keys`
- `GHCR_USERNAME`, `GHCR_TOKEN` secrets

## 11) Post-Deploy Smoke Checklist

1. Frontend reachable on port 3000
2. Backend health `live` + `ready` both pass
3. Register/login works
4. Dashboard loads for authenticated user
5. Worker logs show ingestion cycles without crash loops
