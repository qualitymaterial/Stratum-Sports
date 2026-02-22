#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://134.209.125.6:8000}}"
API_BASE="${BASE_URL%/}/api/v1"

EMAIL="smoke_$(date +%s)_${RANDOM}@example.com"
PASSWORD="$(python3 - <<'PY'
import secrets
print("Sm0ke!" + secrets.token_urlsafe(12))
PY
)"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

register_body="$TMP_DIR/register.json"
login_body="$TMP_DIR/login.json"
me_body="$TMP_DIR/me.json"

payload="$(python3 - <<PY
import json
print(json.dumps({"email": "$EMAIL", "password": "$PASSWORD"}))
PY
)"

register_code="$(
  curl -sS -o "$register_body" -w "%{http_code}" \
    -X POST "${API_BASE}/auth/register" \
    -H "Content-Type: application/json" \
    --data "$payload"
)"
if [[ "$register_code" != "200" ]]; then
  echo "FAIL register status=${register_code}" >&2
  exit 1
fi

login_code="$(
  curl -sS -o "$login_body" -w "%{http_code}" \
    -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    --data "$payload"
)"
if [[ "$login_code" != "200" ]]; then
  echo "FAIL login status=${login_code}" >&2
  exit 1
fi

token="$(
  python3 - "$login_body" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
token = payload.get("access_token", "")
if not token:
    raise SystemExit(1)
print(token)
PY
)"

me_code="$(
  curl -sS -o "$me_body" -w "%{http_code}" \
    "${API_BASE}/auth/me" \
    -H "Authorization: Bearer ${token}"
)"
if [[ "$me_code" != "200" ]]; then
  echo "FAIL auth/me status=${me_code}" >&2
  exit 1
fi

echo "PASS smoke_auth base_url=${BASE_URL%/}"
