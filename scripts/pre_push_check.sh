#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Branch and working tree"
git status --short --branch

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARN: working tree is not clean."
fi

echo "[2/4] Validate production compose config"
docker compose -f docker-compose.prod.yml --env-file .env.production.example config >/dev/null

echo "[3/4] Run critical backend tests"
docker compose run --rm --no-deps backend pytest -q \
  tests/test_performance_intel.py \
  tests/test_odds_api_resilience.py \
  tests/test_consensus.py \
  tests/test_discord_alert_payloads.py

echo "[4/4] Recent commits"
git log --oneline -n 5

echo "Pre-push check complete."
