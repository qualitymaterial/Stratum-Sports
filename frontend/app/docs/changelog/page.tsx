import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Changelog",
  description: "Public documentation change log and deprecation communication structure.",
  path: "/docs/changelog",
});

type ChangeEntry = {
  date: string;
  category: "Docs" | "Auth" | "Webhooks" | "Rate Limits" | "API" | "Security" | "Infrastructure";
  summary: string;
  impact: string;
};

const ENTRIES: ChangeEntry[] = [
  {
    date: "2026-02-28",
    category: "Docs",
    summary: "Institutional Polish Pass: added governance verification notes and full partner/intel endpoint index to API Reference.",
    impact: "No integration change. Informational.",
  },
  {
    date: "2026-02-28",
    category: "Auth",
    summary: "Corrected MFA verify endpoint path in documentation from /auth/mfa/verify to /auth/login/mfa-verify.",
    impact: "Integration correction required if using the incorrect path. No backend behaviour change.",
  },
  {
    date: "2026-02-28",
    category: "Auth",
    summary: "Corrected UserOut response schema in documentation — removed non-existent is_active field; documented actual fields: is_admin, mfa_enabled, has_partner_access, created_at.",
    impact: "Clients parsing is_active from login or /me responses must update field references.",
  },
  {
    date: "2026-02-28",
    category: "Rate Limits",
    summary: "Published real rate-limit parameters: 180 req/min global per-IP limit, 60-second window, X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset response headers.",
    impact: "Clients should begin monitoring X-RateLimit-Remaining on every response.",
  },
  {
    date: "2026-02-28",
    category: "Webhooks",
    summary: "Documented real delivery parameters: 5s timeout, 3 retries, 5s initial backoff, 2× exponential factor. Confirmed X-Stratum-Signature header with sha256= prefix.",
    impact: "Receiver implementations must respond within 5 seconds or the delivery is treated as failed.",
  },
  {
    date: "2026-02-28",
    category: "Docs",
    summary: "Replaced legacy /developers section with institutional /docs hub. All /developer and /developers routes now redirect to /docs.",
    impact: "Update any bookmarks or internal links pointing to /developers.",
  },
  {
    date: "2026-02-24",
    category: "API",
    summary: "Announced Intel API partner access tier with ranked signal feed and quality filters for private integrations.",
    impact: "Additive. Existing integrations unaffected. Partner tier required for /api/v1/intel/* access.",
  },
  {
    date: "2026-02-21",
    category: "Security",
    summary: "Removed JWT-in-query-string pattern for WebSocket authentication. WebSocket auth now uses explicit first-message payload: { type: 'auth', token: '...' }.",
    impact: "Breaking for WebSocket clients using query-string token auth. Update handshake before reconnecting.",
  },
  {
    date: "2026-02-21",
    category: "Security",
    summary: "Added OAuth state token generation, Redis-backed replay guard, and CSRF protection to Discord OAuth callback flow.",
    impact: "No action required for standard API integrators. Discord OAuth clients must persist and validate state parameter.",
  },
  {
    date: "2026-02-21",
    category: "API",
    summary: "Added exponential backoff retry logic to webhook delivery engine with configurable initial delay, backoff factor, and max retries.",
    impact: "Receiver endpoints must be idempotent. Signal events may now arrive up to 3 times before a delivery is marked failed.",
  },
  {
    date: "2026-02-21",
    category: "Infrastructure",
    summary: "Published Infrastructure & Methodology page documenting CLV methodology, regime classification, ingestion architecture, and signal integrity model.",
    impact: "No integration change. Informational.",
  },
];

const CATEGORY_STYLES: Record<ChangeEntry["category"], string> = {
  Docs: "bg-textMute/10 text-textMute",
  Auth: "bg-accent/10 text-accent",
  Webhooks: "bg-accent/10 text-accent",
  "Rate Limits": "bg-textMute/10 text-textMute",
  API: "bg-accent/10 text-accent",
  Security: "bg-red-900/20 text-red-400",
  Infrastructure: "bg-textMute/10 text-textMute",
};

export default function DocsChangelogPage() {
  return (
    <DocsPage
      title="Changelog"
      description="This log tracks externally relevant documentation and interface changes for institutional users."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Release Logging Standard</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Entries cover externally visible docs, API, auth, and security changes only.</li>
          <li>Additive changes (new fields, new endpoints) are always non-breaking.</li>
          <li>Breaking changes are explicitly labeled and include migration actions.</li>
          <li>Deprecation windows of at least 30 days are provided before endpoint or field removal.</li>
        </ul>
      </section>

      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Entries</h2>
        {ENTRIES.map((entry, i) => (
          <div key={i} className="rounded border border-borderTone bg-panelSoft p-4 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-mono text-textMute">{entry.date}</span>
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${CATEGORY_STYLES[entry.category]}`}
              >
                {entry.category}
              </span>
            </div>
            <p className="text-sm text-textMain">{entry.summary}</p>
            <p className="text-xs text-textMute">
              <span className="font-semibold uppercase tracking-wide">Impact:</span>{" "}
              {entry.impact}
            </p>
          </div>
        ))}
      </section>
    </DocsPage>
  );
}
