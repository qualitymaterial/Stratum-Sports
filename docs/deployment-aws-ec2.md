# Stratum Sports Production Deployment (AWS EC2 + Docker Compose)

This runbook deploys Stratum Sports on one Ubuntu EC2 host using Docker Compose.

Note: for the current DigitalOcean + GitHub Actions production flow, use `docs/production-runbook.md`.

## 1) Prerequisites

- AWS account and domain name
- Docker-compatible EC2 instance (recommended starting point: `t3.large`)
- DNS records:
  - `app.stratumsports.com` -> EC2 public IP
  - `api.stratumsports.com` -> EC2 public IP
- API keys ready:
  - The Odds API key
  - Stripe secret key
  - Stripe webhook secret
  - Stripe Pro price id

## 2) Launch EC2

- Ubuntu 22.04/24.04
- Security group inbound:
  - `22` (SSH) from your IP only
  - `3000` from trusted IPs only (or from load balancer)
  - `8000` from trusted IPs only (or from load balancer)
- Attach sufficient storage (at least 40 GB to start)

## 3) Install Docker + Compose

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out and back in, then verify:

```bash
docker --version
docker compose version
```

## 4) Deploy Application

```bash
git clone <your-repo-url> stratum-sports
cd stratum-sports
cp .env.production.example .env.production
```

Edit `.env.production` and fill all real secrets/URLs.

Mandatory before launch:

- `APP_ENV=production`
- Strong `JWT_SECRET`
- Strong DB password and matching `DATABASE_URL`
- `ODDS_API_KEY`
- Stripe keys and price id
- `CORS_ORIGINS=https://app.stratumsports.com`
- `NEXT_PUBLIC_API_BASE_URL=https://api.stratumsports.com/api/v1`
- `FREE_DELAY_MINUTES=10` (spec behavior)

Start:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Check:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f --tail=200
```

## 5) Stripe Webhook Setup

In Stripe Dashboard, set webhook endpoint:

- `https://api.stratumsports.com/api/v1/billing/webhook`

Subscribe to events:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

Put webhook signing secret into `STRIPE_WEBHOOK_SECRET` and restart:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

## 6) DNS + TLS

Recommended production setup:

- Put AWS ALB or reverse proxy in front of `3000` and `8000`
- Terminate TLS at ALB/proxy
- Route:
  - `app.stratumsports.com` -> frontend (`3000`)
  - `api.stratumsports.com` -> backend (`8000`)

## 7) Operational Baseline

- Backups:
  - Nightly `pg_dump` to S3
  - Snapshot EBS volume daily
- Monitoring:
  - Configure `SENTRY_DSN`
  - Alert on container restart loops and 5xx rates
- Security:
  - Restrict SSH to fixed IPs
  - Keep Docker/OS patched
  - Rotate Stripe/JWT/API keys quarterly

## 8) Update Procedure

```bash
cd stratum-sports
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## 9) Rollback

- Checkout previous commit/tag
- Rebuild and restart:

```bash
git checkout <last-known-good-tag>
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## 10) Pre-Market Launch Checklist

- Registration/login tested
- Odds ingestion verified in worker logs
- Signal generation verified on dashboard
- Free/pro gating validated end-to-end
- Stripe checkout and downgrade/upgrade flows validated
- Discord webhook alerts validated for Pro users
- Legal pages live (Terms, Privacy, Disclaimer)
