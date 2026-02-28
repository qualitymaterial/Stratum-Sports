import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

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
        <h2 className="text-xl font-semibold">Global Rate Limit</h2>
        <p className="text-textMute">
          All API traffic is subject to a global per-IP rate limit enforced at the infrastructure layer.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`Window:    60 seconds (per-IP, per-minute bucket)
Limit:     180 requests per minute
Behavior:  Requests exceeding the limit receive HTTP 429.
           The limit resets at the start of each minute.`}
        </pre>
        <h3 className="pt-2 text-base font-semibold">Rate Limit Response Headers</h3>
        <p className="text-textMute">
          Every API response includes the following headers to support proactive throttling on the client side:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Header</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">X-RateLimit-Limit</td>
                <td className="px-3 py-2">integer</td>
                <td className="px-3 py-2">Maximum requests allowed in the current window (180).</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">X-RateLimit-Remaining</td>
                <td className="px-3 py-2">integer</td>
                <td className="px-3 py-2">Requests remaining in the current window.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">X-RateLimit-Reset</td>
                <td className="px-3 py-2">unix timestamp</td>
                <td className="px-3 py-2">Unix timestamp (UTC) when the current window resets.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Partner Monthly Soft Limit</h2>
        <p className="text-textMute">
          Partner API access is additionally subject to a monthly usage soft limit, tracked separately per account.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`Default Monthly Soft Limit:   50,000 requests
Overage:                      Billed transparently at $2.00 per additional unit
                              (TODO: Confirm overage unit quantity per contract)
Tracking:                     Usage is metered via Redis and flushed to the billing ledger.`}
        </pre>
        <p className="text-textMute">
          Partner entitlements are configured individually and may differ from the defaults above. Confirm your specific limits via the billing summary endpoint: <code className="rounded bg-bg px-1.5 py-0.5 text-accent">GET /api/v1/partner/billing-summary</code>.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Billing and Overage</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Usage is metered per request and summarized by billing period.</li>
          <li>Overages are billed transparently per contractual terms via Stripe.</li>
          <li>No free API trial is provided for institutional access.</li>
          <li>Usage history is accessible via <code className="rounded bg-bg px-1 py-0.5 text-accent">GET /api/v1/partner/usage/history</code> (last 12 periods).</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Operational Recommendation</h2>
        <p className="text-textMute">
          Monitor <code className="rounded bg-bg px-1.5 py-0.5 text-accent">X-RateLimit-Remaining</code> on every response. Alert internally at 20% remaining capacity. Add internal throttling and queued retry controls so client systems remain stable during upstream or downstream constraint periods.
        </p>
      </section>
      <DocsVerifiedNote />
    </DocsPage>
  );
}
