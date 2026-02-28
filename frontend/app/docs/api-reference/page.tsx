import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "API Reference",
  description: "Endpoint reference, error model, versioning policy, and request lifecycle documentation for the Stratum API.",
  path: "/docs/api-reference",
});

export default function DocsApiReferencePage() {
  return (
    <DocsPage
      title="API Reference"
      description="This reference documents the Stratum API versioning model, error envelope, and verified endpoint definitions."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">API Versioning</h2>
        <p className="text-textMute">
          All Stratum API endpoints are served under a versioned base path. The current production version is <code className="rounded bg-bg px-1.5 py-0.5 text-accent">v1</code>.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`Base URL: https://<your-host>/api/v1

All requests must include the version prefix.
Breaking changes will not be introduced within a version.
Additive fields may be appended to response schemas without a version bump.`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Error Model</h2>
        <p className="text-textMute">
          All error responses follow the standard FastAPI error envelope. Clients should parse the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">detail</code> field for actionable error context.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`HTTP/1.1 <status_code>
Content-Type: application/json

{
  "detail": "<human-readable error message>"
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Common Status Codes</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Meaning</th>
                <th className="px-3 py-2">Client Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">200</td><td className="px-3 py-2">Success</td><td className="px-3 py-2">Process response body.</td></tr>
              <tr><td className="px-3 py-2 font-mono">400</td><td className="px-3 py-2">Bad Request</td><td className="px-3 py-2">Fix request payload or parameters.</td></tr>
              <tr><td className="px-3 py-2 font-mono">401</td><td className="px-3 py-2">Unauthorized</td><td className="px-3 py-2">Check or refresh bearer token.</td></tr>
              <tr><td className="px-3 py-2 font-mono">403</td><td className="px-3 py-2">Forbidden</td><td className="px-3 py-2">Insufficient tier or role. Contact support.</td></tr>
              <tr><td className="px-3 py-2 font-mono">404</td><td className="px-3 py-2">Not Found</td><td className="px-3 py-2">Verify resource identifier.</td></tr>
              <tr><td className="px-3 py-2 font-mono">429</td><td className="px-3 py-2">Rate Limited</td><td className="px-3 py-2">Back off and retry after cooldown window.</td></tr>
              <tr><td className="px-3 py-2 font-mono">500</td><td className="px-3 py-2">Internal Error</td><td className="px-3 py-2">Retry with exponential backoff. Report if persistent.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">GET /api/v1/health/live</h2>
        <p className="text-textMute">
          Lightweight liveness probe. Returns 200 when the API process is running. No authentication required.
        </p>
        <h3 className="pt-2 text-base font-semibold">Request</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/live`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "status": "ok"
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Field Reference</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Field</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">status</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2">Always &quot;ok&quot; when the process is alive.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">GET /api/v1/health/ready</h2>
        <p className="text-textMute">
          Readiness probe. Returns 200 with dependency health status. No authentication required.
        </p>
        <h3 className="pt-2 text-base font-semibold">Request</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/ready`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "status": "ok",
  "db": true,
  "redis": true
}`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Field Reference</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Field</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">status</td><td className="px-3 py-2">string</td><td className="px-3 py-2">&quot;ok&quot; when all dependencies are healthy; &quot;degraded&quot; otherwise.</td></tr>
              <tr><td className="px-3 py-2 font-mono">db</td><td className="px-3 py-2">boolean</td><td className="px-3 py-2">PostgreSQL connectivity status.</td></tr>
              <tr><td className="px-3 py-2 font-mono">redis</td><td className="px-3 py-2">boolean</td><td className="px-3 py-2">Redis connectivity status.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Additional Endpoints</h2>
        <p className="text-textMute">
          The following endpoint groups are available. Detailed request/response documentation will be published as each group is finalized for external use.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Prefix</th>
                <th className="px-3 py-2">Auth</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">/api/v1/auth/*</td><td className="px-3 py-2">Public / Bearer</td><td className="px-3 py-2">Registration, login, token refresh, password reset.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/dashboard/*</td><td className="px-3 py-2">Bearer</td><td className="px-3 py-2">Dashboard summary cards.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/games/*</td><td className="px-3 py-2">Bearer</td><td className="px-3 py-2">Game listings and event detail.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/intel/*</td><td className="px-3 py-2">Bearer (Pro)</td><td className="px-3 py-2">Signal feed, consensus, CLV analytics, signal quality.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/partner/*</td><td className="px-3 py-2">Bearer (Partner)</td><td className="px-3 py-2">Webhook management, usage, billing summary.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/watchlist/*</td><td className="px-3 py-2">Bearer</td><td className="px-3 py-2">User watchlist management.</td></tr>
              <tr><td className="px-3 py-2 font-mono">/api/v1/billing/*</td><td className="px-3 py-2">Bearer</td><td className="px-3 py-2">Stripe checkout and billing portal sessions.</td></tr>
            </tbody>
          </table>
        </div>
        <p className="text-textMute">
          (TODO: Publish full request/response schemas for intel and partner endpoint groups.)
        </p>
      </section>
    </DocsPage>
  );
}
