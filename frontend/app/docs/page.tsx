import Link from "next/link";

import { DOCS_NAV, createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Overview",
  description: "Institutional documentation hub for Stratum infrastructure, integration, and operational controls.",
  path: "/docs",
});

export default function DocsOverviewPage() {
  return (
    <DocsPage
      title="Docs Overview"
      description="This hub provides implementation, security, billing, and operational documentation for institutional users integrating with Stratum."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">API Version</h2>
        <p className="text-textMute">
          The current production API version is <code className="rounded bg-bg px-1.5 py-0.5 text-accent">v1</code>.
          All endpoints are served under the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">/api/v1</code> base path.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Breaking changes are not introduced within a version.</li>
          <li>Additive fields may be appended to response schemas without a version bump. Clients must tolerate unknown fields.</li>
          <li>Deprecation windows of at least 30 days are provided before removing any endpoint or field.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Documentation Index</h2>
        <p className="text-textMute">
          Each section is structured for implementation teams, security reviewers, and operations stakeholders.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          {DOCS_NAV.filter((item) => item.href !== "/docs").map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded border border-borderTone bg-panelSoft px-4 py-3 transition hover:border-accent"
            >
              <p className="text-sm font-semibold">{item.label}</p>
              <p className="mt-1 text-xs text-textMute">{item.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Signal Integrity</h2>
        <p className="text-textMute">
          Signals are time-locked upon emission and are not modified retroactively. Each signal is immutably logged with a timestamp and cross-referenced with final market consensus for post-event evaluation. No manual filtering or selective reporting is applied.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Data Lineage</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Upstream sources: Live odds data is ingested from The Odds API covering major sportsbook feeds. Exchange data is sourced from Kalshi for regulated prediction market liquidity.</li>
          <li>Refresh cadence: Primary polling operates at 60-second intervals during active events, with adaptive cadence that increases to 15-minute intervals for events more than 3 hours from commencement.</li>
          <li>Retention policy: Odds snapshots and signal history are retained for operational analysis. (TODO: Confirm and publish formal retention window.)</li>
          <li>Backfill: Historical data can be backfilled using internal tooling. Backfilled data is idempotent and deduplicated at the snapshot level.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Documentation Standards</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Public documentation only. No authentication gate.</li>
          <li>Stable, version-aware guidance for institutional integration.</li>
          <li>Explicit placeholders where implementation details are pending.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
