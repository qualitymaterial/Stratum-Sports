# Changelog

All notable changes to this project are documented in this file.

## 2026-02-24

### Added
- Announced paid Intel API partner access ($99/month) with a ranked signal feed and quality filters for private integrations.
- Confirmed nullable-safe, backward-compatible enriched fields for incremental client adoption.

## 2026-02-21

### Added
- Discord OAuth state token generation and validation to prevent CSRF/login-injection flows.
- Redis-backed one-time OAuth state replay guard for Discord callback handling.
- JWT-signed OAuth state helpers in backend security module.
- Daily API credit budget control (`ODDS_API_TARGET_DAILY_CREDITS`) with docs and env templates.
- Production-grade user/operator guide with onboarding, feature usage, troubleshooting, and glossary (`docs/user-guide.md`).
- Unit tests for OAuth state token behavior and adaptive poll interval budgeting.

### Changed
- WebSocket auth moved from URL query token to explicit first-message auth payload (`{ "type": "auth", "token": "..." }`).
- Frontend WebSocket URL now derives from `NEXT_PUBLIC_API_BASE_URL` instead of hardcoded host/port.
- Discord login flow now persists OAuth state client-side and validates it on callback.
- Discord callback returns full user payload shape used by frontend session model.
- Polling interval logic now applies a budget-aware minimum interval based on provider response usage.

### Security
- Removed high-risk JWT-in-query-string pattern for realtime websocket authentication.
- Added OAuth state and replay checks to Discord auth flow.
- Reduced user-identifying details in websocket logs.

### Operational Notes
- Recreate backend/frontend containers after updating to activate security changes:
  - `docker compose up -d --force-recreate backend frontend`
- If using custom websocket clients, update handshake protocol:
  - connect to `/api/v1/realtime/odds`
  - immediately send auth message with token

### Commit
- `ac49da8` — Harden OAuth and websocket auth; add user guide and polling controls
