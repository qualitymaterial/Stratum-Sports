set -eu
cd /opt/stratum-sports
test -f docker-compose.prod.yml
test -f .env.production

git config --global --add safe.directory /opt/stratum-sports || true

# Abort on tracked-file modifications (uncommitted changes that could conflict)
tracked_changes="$(git diff --name-only HEAD 2>/dev/null || true)$(git diff --cached --name-only HEAD 2>/dev/null || true)"
if [ -n "$tracked_changes" ]; then
  echo "ERROR: uncommitted changes to tracked files in /opt/stratum-sports; aborting."
  git status --short || true
  exit 1
fi

# Clean up untracked files (scratch scripts, __pycache__, etc.) so they don't block pulls
untracked="$(git ls-files --others --exclude-standard 2>/dev/null || true)"
if [ -n "$untracked" ]; then
  echo "WARNING: removing untracked files from deploy target:"
  echo "$untracked"
  git clean -fd
fi

# Network Check/Debug: Sometimes droplets experience transient DNS failures during heavy deployment.
echo "--- Checking network / DNS ---"
ping -c 2 github.com || { echo "WARNING: ping to github.com failed. Checking resolvectl and resolv.conf:"; resolvectl status || true; cat /etc/resolv.conf || true; }

# Temporary GitHub DNS Resilience: If git fetch fails because of DNS, retry up to 5 times.
for attempt in {1..5}; do
  if git fetch origin main; then
    break
  fi
  echo "WARNING: git fetch failed on attempt $attempt. Retrying in 10s..."
  sleep 10
  if [ "$attempt" -eq 5 ]; then
    echo "ERROR: git fetch failed after 5 attempts."
    exit 1
  fi
done

git checkout main

for attempt in {1..5}; do
  if git pull --ff-only origin main; then
    break
  fi
  echo "WARNING: git pull failed on attempt $attempt. Retrying in 10s..."
  sleep 10
  if [ "$attempt" -eq 5 ]; then
    echo "ERROR: git pull failed after 5 attempts."
    exit 1
  fi
done

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "ERROR: docker compose plugin (or docker-compose) not found on droplet."
  exit 1
fi
diagnose() {
  compose -f docker-compose.prod.yml --env-file .env.production ps || true
  compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 backend worker frontend db redis || true
}
upsert_env_var() {
  key="$1"
  value="$2"
  if grep -q "^${key}=" .env.production; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env.production
  else
    printf '%s=%s\n' "$key" "$value" >> .env.production
  fi
}
persist_image_env() {
  upsert_env_var BACKEND_IMAGE "$BACKEND_IMAGE"
  upsert_env_var WORKER_IMAGE "$WORKER_IMAGE"
  upsert_env_var FRONTEND_IMAGE "$FRONTEND_IMAGE"
}
get_running_image() {
  service="$1"
  cid="$(compose -f docker-compose.prod.yml --env-file .env.production ps -q "$service" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    return 0
  fi
  docker inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true
}
rollback() {
  if [ "${AUTO_ROLLBACK_ON_FAILURE}" != "true" ]; then
    echo "INFO: auto rollback disabled; skipping rollback."
    return 1
  fi
  if [ -z "${PREV_BACKEND_IMAGE:-}" ] || [ -z "${PREV_WORKER_IMAGE:-}" ] || [ -z "${PREV_FRONTEND_IMAGE:-}" ]; then
    echo "ERROR: previous image refs unavailable; cannot rollback automatically."
    return 1
  fi

  echo "Attempting rollback to previous image set..."
  BACKEND_IMAGE="$PREV_BACKEND_IMAGE"
  WORKER_IMAGE="$PREV_WORKER_IMAGE"
  FRONTEND_IMAGE="$PREV_FRONTEND_IMAGE"
  export BACKEND_IMAGE WORKER_IMAGE FRONTEND_IMAGE
  persist_image_env

  if ! compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans; then
    echo "ERROR: rollback compose up failed"
    diagnose
    return 1
  fi
  if ! compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/live >/dev/null; then
    echo "ERROR: rollback backend health check failed"
    diagnose
    return 1
  fi
  echo "Rollback completed."
  return 0
}
smoke_checks() {
  app_base="${SMOKE_APP_BASE_URL%/}"
  api_base="${SMOKE_API_BASE_URL%/}"

  # Internal health probes (container-local) are authoritative for rollback gating.
  health_ok=0
  for attempt in $(seq 1 20); do
    if compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/live >/dev/null \
      && compose -f docker-compose.prod.yml --env-file .env.production exec -T backend curl -fsS http://localhost:8000/api/v1/health/ready >/dev/null \
      && curl -fsS --max-time 10 http://localhost/ >/dev/null; then
      health_ok=1
      break
    fi
    sleep 3
  done
  if [ "$health_ok" -ne 1 ]; then
    echo "ERROR: internal post-deploy smoke checks failed"
    return 1
  fi

  # External probes enforce canonical host health.
  curl -fsS --max-time 12 "$app_base/" >/dev/null
  curl -fsS --max-time 12 "$api_base/api/v1/health/live" >/dev/null
  curl -fsS --max-time 12 "$api_base/api/v1/health/ready" >/dev/null
}

printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
PREV_BACKEND_IMAGE="$(get_running_image backend)"
PREV_WORKER_IMAGE="$(get_running_image worker)"
PREV_FRONTEND_IMAGE="$(get_running_image frontend)"
BACKEND_IMAGE="ghcr.io/qualitymaterial/stratum-sports-backend:${IMAGE_TAG}"
WORKER_IMAGE="$BACKEND_IMAGE"
FRONTEND_IMAGE="ghcr.io/qualitymaterial/stratum-sports-frontend:${IMAGE_TAG}"
export BACKEND_IMAGE WORKER_IMAGE FRONTEND_IMAGE
persist_image_env
if [ "${BACKEND_IMAGE##*:}" = "latest" ] || [ "${WORKER_IMAGE##*:}" = "latest" ] || [ "${FRONTEND_IMAGE##*:}" = "latest" ]; then
  echo "ERROR: mutable :latest tag detected in deploy image refs"
  echo "BACKEND_IMAGE=$BACKEND_IMAGE"
  echo "WORKER_IMAGE=$WORKER_IMAGE"
  echo "FRONTEND_IMAGE=$FRONTEND_IMAGE"
  exit 1
fi
if [ "$BACKEND_IMAGE" != "ghcr.io/qualitymaterial/stratum-sports-backend:${IMAGE_TAG}" ]; then
  echo "ERROR: BACKEND_IMAGE does not match deploy SHA $IMAGE_TAG: $BACKEND_IMAGE"
  exit 1
fi
if [ "$WORKER_IMAGE" != "ghcr.io/qualitymaterial/stratum-sports-backend:${IMAGE_TAG}" ]; then
  echo "ERROR: WORKER_IMAGE does not match deploy SHA $IMAGE_TAG: $WORKER_IMAGE"
  exit 1
fi
if [ "$FRONTEND_IMAGE" != "ghcr.io/qualitymaterial/stratum-sports-frontend:${IMAGE_TAG}" ]; then
  echo "ERROR: FRONTEND_IMAGE does not match deploy SHA $IMAGE_TAG: $FRONTEND_IMAGE"
  exit 1
fi

if ! compose -f docker-compose.prod.yml --env-file .env.production pull backend worker frontend; then
  echo "ERROR: image pull failed"
  diagnose
  exit 1
fi
if ! compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans; then
  echo "ERROR: compose up failed"
  diagnose
  rollback || true
  exit 1
fi

if ! smoke_checks; then
  echo "ERROR: post-deploy smoke checks failed"
  diagnose
  rollback || true
  exit 1
fi
compose -f docker-compose.prod.yml --env-file .env.production ps
