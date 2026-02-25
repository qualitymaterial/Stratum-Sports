# Admin Control Plane Work Queue

This document turns the `PLAN.md` admin roadmap into actionable implementation slices.

## Current Baseline

1. Admin API is read-only (`/api/v1/admin/overview`, `/api/v1/admin/conversion/funnel`).
2. Admin access is a binary flag (`is_admin`).
3. Promotion and grants still rely on scripts.
4. Admin UI is visibility/reporting only.

## Today Queue (Low-Risk P0 Slice)

1. Add immutable admin audit log foundation.
2. Add scoped admin role model with backward-compatible `is_admin` fallback.
3. Add one admin mutation endpoint with required `reason` and audit write.
4. Add role + audit tests for the new mutation path.

## Next Queue (P0 Completion)

1. User admin APIs: search, tier change, grant/revoke admin, activate/deactivate.
2. Billing admin APIs: subscription view, resync, grace controls.
3. Partner admin APIs: issue/revoke/rotate keys, plan/limit updates.

## UI Expansion Queue (P1)

1. Expand `/app/admin` into tabs: Overview, Users, Billing, API Partners, Ops, Audit Log.
2. Add destructive action safeguards (confirm dialogs + typed confirmation).
3. Show action receipts with action ID and timestamp.

## Reliability and Security Queue (P1/P2)

1. Replace shared ops token with scoped service tokens and rotation.
2. Add step-up auth for sensitive writes.
3. Add MFA for admin users.
4. Enforce privileged session controls (shorter TTL, re-auth on elevation).

## Definition of Done for Admin Control Plane

1. Routine admin operations are UI/API-driven (not script-only).
2. Every admin write is audited with actor, target, reason, before/after.
3. Permissions are role-scoped and test-covered.
4. Sensitive actions require step-up auth.
