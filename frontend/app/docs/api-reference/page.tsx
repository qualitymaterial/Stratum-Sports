import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

export const metadata = createDocsMetadata({
  title: "API Reference",
  description: "Endpoint reference, error model, versioning policy, and request lifecycle documentation for the Stratum API.",
  path: "/docs/api-reference",
});

export default function DocsApiReferencePage() {
  return (
    <DocsPage
      title="API Reference"
      description="This reference documents the Stratum API versioning model, error envelope, verified health endpoints, and partner endpoint index."
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
          All error responses use the standard FastAPI error envelope. Parse the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">detail</code> field for actionable context. No <code className="rounded bg-bg px-1.5 py-0.5 text-accent">request_id</code> is currently included in error responses.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`HTTP/1.1 <status_code>
Content-Type: application/json

{
  "detail": "<human-readable error message>"
}`}
        </pre>

        <h3 className="pt-2 text-base font-semibold">Error Semantics</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Meaning</th>
                <th className="px-3 py-2">Backend Behavior</th>
                <th className="px-3 py-2">Client Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">200</td>
                <td className="px-3 py-2">Success</td>
                <td className="px-3 py-2">Request completed.</td>
                <td className="px-3 py-2">Process response body.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">400</td>
                <td className="px-3 py-2">Bad Request</td>
                <td className="px-3 py-2">Validation failure (e.g. password policy, duplicate email, invalid token).</td>
                <td className="px-3 py-2">Fix request payload before retrying.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">401</td>
                <td className="px-3 py-2">Unauthorized</td>
                <td className="px-3 py-2">Missing, invalid, expired, or revoked bearer token or API key. Detail includes: <em>Invalid credentials</em>, <em>Invalid token</em>, <em>API key revoked</em>, <em>API key expired</em>, <em>Inactive user</em>.</td>
                <td className="px-3 py-2">Re-authenticate or rotate credentials.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">403</td>
                <td className="px-3 py-2">Forbidden</td>
                <td className="px-3 py-2">Authenticated but insufficient tier or role. Detail includes: <em>Pro subscription required</em>, <em>API access not enabled</em>, <em>Admin access required</em>.</td>
                <td className="px-3 py-2">Upgrade plan or contact support.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">404</td>
                <td className="px-3 py-2">Not Found</td>
                <td className="px-3 py-2">Resource does not exist or does not belong to the authenticated user.</td>
                <td className="px-3 py-2">Verify resource identifier.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">429</td>
                <td className="px-3 py-2">Rate Limited</td>
                <td className="px-3 py-2">Per-IP limit of 180 req/min exceeded. Detail: <em>Rate limit exceeded</em>. Retry after checking <code className="rounded bg-bg px-1 py-0.5">X-RateLimit-Reset</code>.</td>
                <td className="px-3 py-2">Back off. Do not retry immediately.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">500</td>
                <td className="px-3 py-2">Internal Error</td>
                <td className="px-3 py-2">Unhandled server-side failure.</td>
                <td className="px-3 py-2">Retry with exponential backoff. Report if persistent.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">503</td>
                <td className="px-3 py-2">Service Unavailable</td>
                <td className="px-3 py-2">Redis unavailable (partner usage endpoints). Detail: <em>Redis unavailable</em>.</td>
                <td className="px-3 py-2">Retry after dependency recovers.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">GET /api/v1/health/live</h2>
        <p className="text-textMute">
          Liveness probe. Returns 200 when the API process is running. No authentication required.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/live`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{ "status": "ok" }`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">GET /api/v1/health/ready</h2>
        <p className="text-textMute">
          Readiness probe. Returns dependency health for PostgreSQL and Redis. No authentication required.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`curl -s https://<your-host>/api/v1/health/ready`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Response (200 OK)</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`{
  "status": "ok | degraded",
  "db": true,
  "redis": true
}`}
        </pre>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Field</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">status</td><td className="px-3 py-2">string</td><td className="px-3 py-2">&quot;ok&quot; when all dependencies reachable; &quot;degraded&quot; otherwise.</td></tr>
              <tr><td className="px-3 py-2 font-mono">db</td><td className="px-3 py-2">boolean</td><td className="px-3 py-2">PostgreSQL connectivity status.</td></tr>
              <tr><td className="px-3 py-2 font-mono">redis</td><td className="px-3 py-2">boolean</td><td className="px-3 py-2">Redis connectivity status.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Intel Endpoints (Pro / Partner)</h2>
        <p className="text-textMute">
          The following endpoints are available under <code className="rounded bg-bg px-1.5 py-0.5 text-accent">/api/v1/intel</code>. All require a Pro or Partner bearer token, or a valid <code className="rounded bg-bg px-1.5 py-0.5 text-accent">stratum_pk_</code> API key. Detailed request/response schemas are pending publication.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2">Path</th>
                <th className="px-3 py-2">Purpose</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/consensus</td>
                <td className="px-3 py-2">Historical consensus data for a given event and market.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/consensus/latest</td>
                <td className="px-3 py-2">Latest consensus snapshot for a given event.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/clv</td>
                <td className="px-3 py-2">Closing line value records filtered by event, sport, market, or strength.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/clv/summary</td>
                <td className="px-3 py-2">Aggregated CLV performance summary across signal types and markets.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/clv/recap</td>
                <td className="px-3 py-2">Daily or weekly CLV recap across a rolling date window.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/clv/scorecards</td>
                <td className="px-3 py-2">Trust scorecards ranking signal types by CLV reliability.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/clv/export.csv</td>
                <td className="px-3 py-2">CSV export of CLV records (max 10,000 rows). Pro/Partner only.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/opportunities</td>
                <td className="px-3 py-2">Current best opportunities scored by edge, strength, and market width.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/signals/quality</td>
                <td className="px-3 py-2">Signal quality index with alert-rule filtering and strength thresholds.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/signals/weekly-summary</td>
                <td className="px-3 py-2">Weekly signal quality summary across a rolling window.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/signals/lifecycle</td>
                <td className="px-3 py-2">Signal lifecycle stages and distribution over a rolling window.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/books/actionable</td>
                <td className="px-3 py-2">Actionable book card for a specific event and signal.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/intel/books/actionable/batch</td>
                <td className="px-3 py-2">Batch actionable book cards for multiple signals on an event.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-textMute">
          Full schemas for the 3 highest-value endpoints are documented below. Remaining endpoint schemas are pending publication.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">GET /api/v1/intel/opportunities</h2>
        <p className="text-textMute">
          Returns current best opportunities ranked by edge, signal strength, and market width. Requires Pro or Partner auth.
        </p>
        <h3 className="pt-1 text-base font-semibold">Query Parameters</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Param</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Default</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">days</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">2</td><td className="px-3 py-2">Lookback window in days (1–30).</td></tr>
              <tr><td className="px-3 py-2 font-mono">sport_key</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by sport (e.g. basketball_nba).</td></tr>
              <tr><td className="px-3 py-2 font-mono">market</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by market: spreads, totals, h2h.</td></tr>
              <tr><td className="px-3 py-2 font-mono">min_strength</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Minimum signal strength score (1–100).</td></tr>
              <tr><td className="px-3 py-2 font-mono">limit</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">10</td><td className="px-3 py-2">Max results (1–50).</td></tr>
            </tbody>
          </table>
        </div>
        <h3 className="pt-1 text-base font-semibold">Response — Array of OpportunityPoint</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`[
  {
    "signal_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "event_id": "nba_20260301_lakers_celtics",
    "game_label": "Lakers @ Celtics",
    "game_commence_time": "2026-03-01T23:00:00Z",
    "signal_type": "steam",
    "display_type": "Steam Move",
    "market": "spreads",
    "outcome_name": "Celtics -4.5",
    "direction": "DOWN",
    "strength_score": 82,
    "created_at": "2026-03-01T21:14:00Z",
    "best_book_key": "draftkings",
    "best_line": -4.0,
    "best_price": -110,
    "consensus_line": -4.5,
    "consensus_price": -112,
    "best_delta": 0.5,
    "best_edge_line": 0.5,
    "best_edge_prob": 0.021,
    "market_width": 1.8,
    "delta_type": "line",
    "books_considered": 7,
    "freshness_seconds": 42,
    "freshness_bucket": "Fresh",
    "execution_rank": 1,
    "clv_prior_samples": 38,
    "clv_prior_pct_positive": 0.71,
    "opportunity_score": 87,
    "context_score": null,
    "blended_score": null,
    "ranking_score": 87,
    "score_basis": "opportunity",
    "score_components": { "strength": 30, "edge": 25, "freshness": 20, "clv_prior": 12 },
    "score_summary": "Strong steam with positive CLV and live edge.",
    "opportunity_status": "ACTIONABLE",
    "reason_tags": ["steam_move", "live_edge", "clv_positive"],
    "actionable_reason": "DraftKings is off consensus; edge present."
  }
]`}
        </pre>
        <h3 className="pt-1 text-base font-semibold">Key Fields</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Field</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">signal_id</td><td className="px-3 py-2">UUID</td><td className="px-3 py-2">Stable unique identifier for the signal. Use for deduplication.</td></tr>
              <tr><td className="px-3 py-2 font-mono">strength_score</td><td className="px-3 py-2">integer 1–100</td><td className="px-3 py-2">Signal confidence. Higher is stronger.</td></tr>
              <tr><td className="px-3 py-2 font-mono">opportunity_status</td><td className="px-3 py-2">string</td><td className="px-3 py-2">ACTIONABLE, MONITOR, or STALE.</td></tr>
              <tr><td className="px-3 py-2 font-mono">best_delta</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Line or probability gap between best book and consensus.</td></tr>
              <tr><td className="px-3 py-2 font-mono">freshness_bucket</td><td className="px-3 py-2">string</td><td className="px-3 py-2">Fresh / Aging / Stale — derived from freshness_seconds.</td></tr>
              <tr><td className="px-3 py-2 font-mono">clv_prior_pct_positive</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Historical positive CLV rate for this signal type. null if insufficient samples.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">GET /api/v1/intel/signals/quality</h2>
        <p className="text-textMute">
          Returns the active signal quality feed with lifecycle stage, alert decisions, and freshness metadata. Requires Pro or Partner auth.
        </p>
        <h3 className="pt-1 text-base font-semibold">Query Parameters</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Param</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Default</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">sport_key</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by sport.</td></tr>
              <tr><td className="px-3 py-2 font-mono">signal_type</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by type: steam, dislocation, exchange_divergence.</td></tr>
              <tr><td className="px-3 py-2 font-mono">market</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by market: spreads, totals, h2h.</td></tr>
              <tr><td className="px-3 py-2 font-mono">min_strength</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Minimum strength score (1–100).</td></tr>
              <tr><td className="px-3 py-2 font-mono">limit</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">50</td><td className="px-3 py-2">Max results (1–200).</td></tr>
            </tbody>
          </table>
        </div>
        <h3 className="pt-1 text-base font-semibold">Response — Array of SignalQualityPoint</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "event_id": "nba_20260301_lakers_celtics",
    "game_label": "Lakers @ Celtics",
    "game_commence_time": "2026-03-01T23:00:00Z",
    "market": "spreads",
    "signal_type": "steam",
    "display_type": "Steam Move",
    "direction": "DOWN",
    "strength_score": 82,
    "time_bucket": "PRETIP",
    "books_affected": 5,
    "window_minutes": 3,
    "created_at": "2026-03-01T21:14:00Z",
    "outcome_name": "Celtics -4.5",
    "book_key": "pinnacle",
    "delta": -0.5,
    "dispersion": 0.8,
    "freshness_seconds": 42,
    "freshness_bucket": "Fresh",
    "lifecycle_stage": "live",
    "lifecycle_reason": "Within active event window",
    "alert_decision": "SEND",
    "alert_reason": "Strength above threshold",
    "metadata": {}
  }
]`}
        </pre>
        <h3 className="pt-1 text-base font-semibold">Key Fields</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Field</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">id</td><td className="px-3 py-2">UUID</td><td className="px-3 py-2">Signal identifier. Use for deduplication and webhook correlation.</td></tr>
              <tr><td className="px-3 py-2 font-mono">time_bucket</td><td className="px-3 py-2">string</td><td className="px-3 py-2">OPEN, MID, LATE, PRETIP, INPLAY, or UNKNOWN — market timing classification.</td></tr>
              <tr><td className="px-3 py-2 font-mono">lifecycle_stage</td><td className="px-3 py-2">string</td><td className="px-3 py-2">live, stale, or resolved.</td></tr>
              <tr><td className="px-3 py-2 font-mono">alert_decision</td><td className="px-3 py-2">string</td><td className="px-3 py-2">SEND or FILTERED — whether this signal passed alerting rules.</td></tr>
              <tr><td className="px-3 py-2 font-mono">dispersion</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Spread across book prices at time of detection. Lower is tighter consensus.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">GET /api/v1/intel/clv</h2>
        <p className="text-textMute">
          Returns closing line value records for signals where final market prices were captured. Used for performance attribution. Requires Pro or Partner auth.
        </p>
        <h3 className="pt-1 text-base font-semibold">Query Parameters</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Param</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Default</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">days</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">30</td><td className="px-3 py-2">Lookback window (1–90).</td></tr>
              <tr><td className="px-3 py-2 font-mono">event_id</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter to a single event.</td></tr>
              <tr><td className="px-3 py-2 font-mono">signal_type</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by signal type.</td></tr>
              <tr><td className="px-3 py-2 font-mono">market</td><td className="px-3 py-2">string</td><td className="px-3 py-2">null</td><td className="px-3 py-2">Filter by market.</td></tr>
              <tr><td className="px-3 py-2 font-mono">limit</td><td className="px-3 py-2">integer</td><td className="px-3 py-2">100</td><td className="px-3 py-2">Max results (1–1000).</td></tr>
            </tbody>
          </table>
        </div>
        <h3 className="pt-1 text-base font-semibold">Response — Array of ClvRecordPoint</h3>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`[
  {
    "signal_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "event_id": "nba_20260228_heat_bucks",
    "signal_type": "steam",
    "market": "spreads",
    "outcome_name": "Bucks -3.5",
    "strength_score": 78,
    "entry_line": -3.5,
    "entry_price": -112,
    "close_line": -5.0,
    "close_price": -110,
    "clv_line": 1.5,
    "clv_prob": 0.034,
    "computed_at": "2026-02-28T02:10:00Z"
  }
]`}
        </pre>
        <h3 className="pt-1 text-base font-semibold">Key Fields</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr><th className="px-3 py-2">Field</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Description</th></tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr><td className="px-3 py-2 font-mono">entry_line / entry_price</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Market line and juice at signal detection time.</td></tr>
              <tr><td className="px-3 py-2 font-mono">close_line / close_price</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Market line and juice at event close (tipoff).</td></tr>
              <tr><td className="px-3 py-2 font-mono">clv_line</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Closing line value in points. Positive = signal beat the close.</td></tr>
              <tr><td className="px-3 py-2 font-mono">clv_prob</td><td className="px-3 py-2">float | null</td><td className="px-3 py-2">Closing line value in probability units. Positive = signal beat the close.</td></tr>
              <tr><td className="px-3 py-2 font-mono">computed_at</td><td className="px-3 py-2">datetime</td><td className="px-3 py-2">ISO 8601 timestamp when CLV was computed post-event.</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Partner Endpoints</h2>
        <p className="text-textMute">
          The following endpoints are available under <code className="rounded bg-bg px-1.5 py-0.5 text-accent">/api/v1/partner</code>. All require a bearer token or <code className="rounded bg-bg px-1.5 py-0.5 text-accent">stratum_pk_</code> API key with partner entitlement enabled.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2">Path</th>
                <th className="px-3 py-2">Purpose</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks</td>
                <td className="px-3 py-2">List all registered webhooks for the authenticated partner.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">POST</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks</td>
                <td className="px-3 py-2">Register a new webhook endpoint (max 5 per partner).</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">PATCH</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks/{"{webhook_id}"}</td>
                <td className="px-3 py-2">Update URL, description, or active state for a webhook.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">POST</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks/{"{webhook_id}"}/secret</td>
                <td className="px-3 py-2">Rotate the HMAC signing secret for a webhook.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">DELETE</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks/{"{webhook_id}"}</td>
                <td className="px-3 py-2">Remove a registered webhook.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/webhooks/logs</td>
                <td className="px-3 py-2">Delivery logs for webhook attempts (max 200 records, filterable by webhook_id).</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/usage</td>
                <td className="px-3 py-2">Current-month usage, monthly limit, remaining, and overage count.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/billing-summary</td>
                <td className="px-3 py-2">Plan details, current usage, and recent usage history (last 6 periods).</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">GET</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/usage/history</td>
                <td className="px-3 py-2">Historical usage periods (max 12). Supports pagination via limit/offset.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">POST</td>
                <td className="px-3 py-2 font-mono">/api/v1/partner/portal</td>
                <td className="px-3 py-2">Create a Stripe billing portal session for plan management.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-textMute">
          (TODO: Publish full request/response schemas for partner webhook and billing endpoints.)
        </p>
      </section>

      <DocsVerifiedNote />
    </DocsPage>
  );
}
