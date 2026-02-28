import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

export const metadata = createDocsMetadata({
  title: "Quickstart",
  description: "Initial setup sequence for institutional teams onboarding to Stratum data delivery.",
  path: "/docs/quickstart",
});

export default function DocsQuickstartPage() {
  return (
    <DocsPage
      title="Quickstart"
      description="Use this checklist to move from access approval to controlled production rollout."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">1. Access Provisioning</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Confirm organizational owner and technical contact.</li>
          <li>Provision credentials in your secure secret manager.</li>
          <li>Document environment separation for sandbox and production.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">2. Environment Configuration</h2>
        <p className="text-textMute">
          The API base URL is resolved from <code className="rounded bg-bg px-1.5 py-0.5 text-accent">NEXT_PUBLIC_API_BASE_URL</code> (or equivalent framework env var). Set the following in your environment:
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`# API base — defaults to http://localhost:8000/api/v1 in local development.
# Set to your production host in deployment.
NEXT_PUBLIC_API_BASE_URL="https://<your-host>/api/v1"

# API key for partner/server-side requests (prefix: stratum_pk_)
# Issued upon partner access approval. Store in a secrets manager; never commit.
STRATUM_API_KEY="stratum_pk_<hex>"

# Webhook signing secret (prefix: whsec_)
# Retrieve from GET /api/v1/partner/webhooks after registration.
STRATUM_WEBHOOK_SECRET="whsec_<hex>"`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">3. First Call — Liveness Check</h2>
        <p className="text-textMute">
          Verify connectivity with the unauthenticated liveness probe before implementing auth flows.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/live

# Expected response:
{ "status": "ok" }`}
        </pre>
        <p className="text-textMute">
          Also check dependency health (PostgreSQL + Redis):
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/ready

# Expected response:
{ "status": "ok", "db": true, "redis": true }`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">4. Auth + Identity Check</h2>
        <p className="text-textMute">
          Obtain a JWT, then verify it by calling the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">/me</code> endpoint.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`# Step 1 — Login (replace email/password with your credentials)
curl -s -X POST https://<your-host>/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email": "your@email.com", "password": "your-password"}'

# Response includes access_token:
# {
#   "access_token": "eyJhbGci...",
#   "token_type": "bearer",
#   "mfa_required": false,
#   "user": { "id": "...", "email": "...", "tier": "pro", ... }
# }

# Step 2 — Verify token identity
curl -s https://<your-host>/api/v1/auth/me \\
  -H "Authorization: Bearer <access_token>"

# Expected: UserOut object with id, email, tier, mfa_enabled, etc.`}
        </pre>
        <p className="text-textMute">
          If your account has MFA enabled, the login response returns <code className="rounded bg-bg px-1.5 py-0.5 text-accent">mfa_challenge_token</code> instead. Submit it with your TOTP code to <code className="rounded bg-bg px-1.5 py-0.5 text-accent">POST /api/v1/auth/login/mfa-verify</code>. See the <a href="/docs/authentication" className="text-accent underline underline-offset-2">Authentication</a> page for the full MFA flow.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">5. First Integration Pass</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Implement authentication and token handling from the <a href="/docs/authentication" className="text-accent underline underline-offset-2">Authentication</a> guide.</li>
          <li>Implement webhook signature validation before any downstream execution. See <a href="/docs/webhooks" className="text-accent underline underline-offset-2">Webhooks</a>.</li>
          <li>Implement <code className="rounded bg-bg px-1 py-0.5">signal_id</code>-based deduplication and replay protection before enabling automation.</li>
          <li>Wire <code className="rounded bg-bg px-1 py-0.5">X-RateLimit-Remaining</code> to internal alerting. See <a href="/docs/rate-limits-and-billing" className="text-accent underline underline-offset-2">Rate Limits</a>.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">6. Go-Live Readiness Checklist</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Security review completed and credentials stored in secrets manager.</li>
          <li>Webhook HMAC verification implemented and tested against a real delivery.</li>
          <li>Replay protection enabled (timestamp window + <code className="rounded bg-bg px-1 py-0.5">signal_id</code> deduplication store).</li>
          <li>Rate-limit monitoring connected to on-call alerting.</li>
          <li>Rollback and incident response runbook approved.</li>
          <li>Health endpoints (<code className="rounded bg-bg px-1 py-0.5">/health/live</code>, <code className="rounded bg-bg px-1 py-0.5">/health/ready</code>) integrated into your uptime monitor.</li>
        </ul>
      </section>

      <DocsVerifiedNote />
    </DocsPage>
  );
}
