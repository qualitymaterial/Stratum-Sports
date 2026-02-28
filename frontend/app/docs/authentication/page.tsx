import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

export const metadata = createDocsMetadata({
  title: "Authentication",
  description: "Authentication model, JWT bearer token handling, MFA flow, and credential lifecycle for Stratum API access.",
  path: "/docs/authentication",
});

export default function DocsAuthenticationPage() {
  return (
    <DocsPage
      title="Authentication"
      description="Authentication controls are designed for institutional environments that require strict credential governance."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Authentication Model</h2>
        <p className="text-textMute">
          Stratum uses JSON Web Tokens (JWT) for API authentication. Obtain a token via the login endpoint and include it as a Bearer token in subsequent requests. Partner integrations may alternatively authenticate using long-lived API keys with a <code className="rounded bg-bg px-1.5 py-0.5 text-accent">stratum_pk_</code> prefix.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Transport credentials only over encrypted channels (HTTPS).</li>
          <li>Use server-side credential storage; never expose tokens in client-side code or URL query strings.</li>
          <li>Implement scoped access based on least privilege.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Step 1 — Login</h2>
        <p className="text-textMute">
          Submit credentials to obtain an access token. If MFA is not enabled, a full access token is issued immediately.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your-password"
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response — No MFA (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "mfa_required": false,
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "user@example.com",
    "tier": "pro",
    "is_admin": false,
    "mfa_enabled": false,
    "has_partner_access": false,
    "created_at": "2026-01-15T10:00:00Z"
  }
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response — MFA Required (200 OK)</h3>
        <p className="text-textMute">
          If MFA is enrolled on the account, the login response contains a short-lived <code className="rounded bg-bg px-1.5 py-0.5 text-accent">mfa_challenge_token</code> instead of an <code className="rounded bg-bg px-1.5 py-0.5 text-accent">access_token</code>. The challenge token expires in 5 minutes.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "access_token": null,
  "token_type": "bearer",
  "mfa_required": true,
  "mfa_challenge_token": "eyJhbGci...<short-lived challenge>",
  "user": null
}`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Step 2 — MFA Verification (if required)</h2>
        <p className="text-textMute">
          This is a continuation of the login flow, not a standalone endpoint. Submit the challenge token obtained in Step 1 together with the TOTP code from your authenticator app. Backup codes are also accepted.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`POST /api/v1/auth/login/mfa-verify
Content-Type: application/json

{
  "mfa_challenge_token": "eyJhbGci...",
  "mfa_code": "123456"
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK) — TokenResponse</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "user@example.com",
    "tier": "pro",
    "is_admin": false,
    "mfa_enabled": true,
    "has_partner_access": false,
    "created_at": "2026-01-15T10:00:00Z"
  }
}`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Using the Token</h2>
        <p className="text-textMute">
          Include the access token in the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">Authorization</code> header for all authenticated requests:
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/auth/me \\
  -H "Authorization: Bearer <access_token>"`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "tier": "pro",
  "is_admin": false,
  "mfa_enabled": false,
  "has_partner_access": false,
  "created_at": "2026-01-15T10:00:00Z"
}`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Credential Lifecycle</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Standard tokens expire after 24 hours (<code className="rounded bg-bg px-1 py-0.5">access_token_expire_minutes: 1440</code>). Re-authenticate to obtain a fresh token.</li>
          <li>Admin tokens use a 4-hour expiration window.</li>
          <li>MFA challenge tokens expire after 5 minutes.</li>
          <li>Password reset is available via <code className="rounded bg-bg px-1.5 py-0.5 text-accent">POST /api/v1/auth/password-reset/request</code> and <code className="rounded bg-bg px-1.5 py-0.5 text-accent">POST /api/v1/auth/password-reset/confirm</code>.</li>
          <li>Password reset tokens expire after 30 minutes.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Access Tiers</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Tier</th>
                <th className="px-3 py-2">Access Scope</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">free</td><td className="px-3 py-2">Delayed odds (10-min), limited watchlist (3 items), redacted signal details.</td></tr>
              <tr><td className="px-3 py-2 font-mono">pro</td><td className="px-3 py-2">Real-time data, full signal feed, CLV analytics, CSV export, Discord alerts.</td></tr>
              <tr><td className="px-3 py-2 font-mono">partner</td><td className="px-3 py-2">Pro access plus webhook delivery, API key auth, usage metering, and billing portal.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <DocsVerifiedNote />
    </DocsPage>
  );
}
