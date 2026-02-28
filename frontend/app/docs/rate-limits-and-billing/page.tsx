import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Rate Limits & Billing",
  description: "Usage governance, rate-limit posture, and overage billing standards for institutional access.",
  path: "/docs/rate-limits-and-billing",
});

export default function DocsRateLimitsAndBillingPage() {
  return (
    <DocsPage
      title="Rate Limits & Billing"
      description="Institutional access uses soft limit enforcement and transparent overage accounting to preserve service continuity."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Rate-Limit Policy</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Soft request limits apply by account tier.</li>
          <li>Limit windows and thresholds are environment-specific.</li>
          <li>Monitoring should treat approaching limits as operational alerts.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Limit Definitions</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`Window: (TODO: Replace with real rate-limit window)
Soft Limit: (TODO: Replace with real request threshold)
Burst Limit: (TODO: Replace with real burst threshold)
Limit Header Names: (TODO: Replace with real header names)`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Billing and Overage</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Usage is metered and summarized by billing period.</li>
          <li>Overages are billed transparently per contractual terms.</li>
          <li>No free API trial is provided for institutional access.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Operational Recommendation</h2>
        <p className="text-textMute">
          Add internal throttling and queued retry controls so client systems remain stable during upstream or downstream constraint periods.
        </p>
      </section>
    </DocsPage>
  );
}
