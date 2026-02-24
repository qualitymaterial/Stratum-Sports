# Stratum Production Runbook (DigitalOcean + GitHub Actions)

This is the primary runbook for deploying, verifying, and rolling back Stratum in production.

## Command Context Legend

- `[Mac]` run in your local Mac terminal (`briananderson@Mac ...`)
- `[Droplet]` run on the server shell (`root@...`)
- `[GitHub UI]` run in the GitHub web interface

If you are at a `root@...` prompt, do not run `pbcopy` or Mac key commands there.

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

### 1.3 Ensure production env file exists

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

## 2) Standard Deploy (Preferred)

### 2.1 Trigger deploy workflow

`[GitHub UI]` Actions -> **Deploy to DigitalOcean** -> **Run workflow** on `main`.

The workflow performs:

- CI verification for target SHA
- backend/frontend image build + push to GHCR
- SSH deploy on droplet
- backend health checks (`/health/live` + `/health/ready`)

### 2.2 Verify deployment

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

## 3) Emergency Manual Deploy by SHA

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

## 4) Rollback (Fast, Reversible)

1. Find previous known-good image SHA.
2. Redeploy with that SHA:

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

3. Re-run health checks from section 2.2.

## 5) Env Sync and Safe Restart

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

## 6) Quick Diagnostics

### 6.1 Backend restarting

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

### 6.2 App login fails with 500

```bash
# [Droplet]
cd /opt/stratum-sports
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 backend
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready
```

### 6.3 GitHub deploy fails with SSH/auth errors

Check:

- `DROPLET_HOST`, `DROPLET_USER`, `DROPLET_SSH_KEY` secrets
- matching public key in `/root/.ssh/authorized_keys`
- `GHCR_USERNAME`, `GHCR_TOKEN` secrets

## 7) Post-Deploy Smoke Checklist

1. Frontend reachable on port 3000
2. Backend health `live` + `ready` both pass
3. Register/login works
4. Dashboard loads for authenticated user
5. Worker logs show ingestion cycles without crash loops

