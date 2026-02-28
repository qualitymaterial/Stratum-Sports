import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

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
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`STRATUM_API_BASE_URL="(TODO: Replace with real API base URL)"
STRATUM_API_KEY="(TODO: Replace with real credential)"
STRATUM_WEBHOOK_SECRET="(TODO: Replace with webhook signing secret)"`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">3. First Integration Pass</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Implement authentication and token handling from the Authentication guide.</li>
          <li>Implement webhook signature validation before any downstream execution.</li>
          <li>Define retry and idempotency strategy before enabling automation.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">4. Go-Live Readiness Checklist</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Security review completed.</li>
          <li>Replay protection enabled.</li>
          <li>Rate-limit monitoring connected to on-call alerting.</li>
          <li>Rollback and incident response runbook approved.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
