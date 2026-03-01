# Admin Control Plane

The Stratum Admin Control Plane is an institutional-grade security and operations dashboard built directly into the web app (`/app/admin`). It replaces manual script-based operations with auditable, UI-driven governance.

## 1. Security & Authentication Models

### Role-Based Access Control (RBAC)
Admin access is no longer a binary flag. Instead, users are assigned granular scopes to ensure principle-of-least-privilege:
*   `super_admin`: Full access to mutations, billing, and system configuration.
*   `ops_admin`: Access to system health, logs, and webhook delivery overrides.
*   `billing_admin`: Access to Stripe integrations, usage limits, and partner tiering.
*   `support_admin`: Read-only access or low-level account remediation.

### Privileged Session Hardening
*   **Time-To-Live (TTL):** While standard user sessions last 24 hours, an Admin session expires after 4 hours.
*   **Multi-Factor Authentication (MFA):** Admin accounts support TOTP-based MFA (Time-based One-Time Password) using a two-phase login flow.
*   **Step-Up Authentication:** Sensitive destructive actions (like suspending a partner or resetting a password) require re-authentication (password confirmation + MFA code) at the moment of mutation.

## 2. The Audit Trail

Transparency is guaranteed by an immutable **Audit Log** that tracks every action taken by an admin.

Each action receipt includes:
1.  **Actor:** The Admin UUID who executed the mutation.
2.  **Target:** The affected endpoint or User UUID.
3.  **Action Type:** Example: `partner.key.rotated`
4.  **Delta:** A "Before & After" JSON payload of the state change.
5.  **Reason:** Mandatory text justification for why the action was taken.

## 3. Operations & Telemetry

The `Operations` tab exposes backend subsystem health to the administrative team without requiring SSH access to the droplet:

*   **Poller Health:** Monitor the uptime and cycle lock status of the primary odds ingestion worker.
*   **Backfill Triggers:** Manually trigger historical data backfilling (bounded by rate limits) via the UI.
*   **Alert Replay:** Re-dispatch Webhook payloads or Discord alerts that may have failed delivery.
*   **Scoped Service Tokens:** Instead of a single static `OPS_INTERNAL_TOKEN`, admins can rotate and revoke time-bound service tokens for external automation scripts.

## 4. API Partner Lifecycle Management

The `API Partners` tab allows administrators to manage institutional consumers:

*   **Key Issuance:** Generate and rotate REST API tokens for partners with one-time reveal.
*   **Limit Enforcement:** Instantly upgrade a partner's rate limit or monthly data allowance.
*   **Anomaly Dashboards:** Visibility into which partners are approaching or exceeding their 50k monthly soft-limit quotas.
