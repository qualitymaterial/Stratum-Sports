import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Status",
  description: "Operational status, uptime targets, incident communication model, and maintenance window policy.",
  path: "/docs/status",
});

export default function DocsStatusPage() {
  return (
    <DocsPage
      title="Status"
      description="Operational status documentation for service health, incident communication, and maintenance governance."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Health Endpoints</h2>
        <p className="text-textMute">
          Stratum exposes two unauthenticated health probes for operational monitoring:
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li><code className="rounded bg-bg px-1.5 py-0.5 text-accent">GET /api/v1/health/live</code> — Returns 200 when the API process is running.</li>
          <li><code className="rounded bg-bg px-1.5 py-0.5 text-accent">GET /api/v1/health/ready</code> — Returns 200 with database and Redis connectivity status. Reports &quot;degraded&quot; if any dependency is unreachable.</li>
        </ul>
        <p className="text-textMute">
          Institutional integrators should poll the readiness endpoint at a cadence appropriate for their SLA requirements.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Uptime Target</h2>
        <p className="text-textMute">
          Stratum targets 99.9% monthly uptime for core API and webhook delivery services, excluding scheduled maintenance windows.
          (TODO: Confirm and publish formal SLA terms when contractual commitments are finalized.)
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Incident Severity Model</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Severity</th>
                <th className="px-3 py-2">Definition</th>
                <th className="px-3 py-2">Initial Notice</th>
                <th className="px-3 py-2">Update Cadence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">SEV-1</td>
                <td className="px-3 py-2">Broad service impairment with material delivery impact.</td>
                <td className="px-3 py-2">Within 15 minutes of detection.</td>
                <td className="px-3 py-2">Every 30 minutes until resolved.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">SEV-2</td>
                <td className="px-3 py-2">Partial service degradation with constrained scope.</td>
                <td className="px-3 py-2">Within 30 minutes of detection.</td>
                <td className="px-3 py-2">Every 60 minutes until resolved.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">SEV-3</td>
                <td className="px-3 py-2">Localized issue with workaround available.</td>
                <td className="px-3 py-2">Within 2 hours of detection.</td>
                <td className="px-3 py-2">Daily until resolved.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-textMute">
          Resolution summaries are published after incident closure.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Maintenance Windows</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Scheduled maintenance is communicated at least 48 hours in advance.</li>
          <li>Maintenance windows are targeted to low-activity periods to minimize delivery disruption.</li>
          <li>Emergency maintenance may be performed with shorter notice when required for security or data integrity.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Breaking Change Policy</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>No silent breaking changes. All behavioral modifications to API responses, webhook payloads, or authentication flows are communicated before deployment.</li>
          <li>Additive fields may be appended to JSON responses without prior notice. Clients must tolerate unknown fields.</li>
          <li>Deprecation windows of at least 30 days are provided before removing any endpoint or field.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Public Status Page</h2>
        <p className="text-textMute">
          A hosted public status dashboard is not yet deployed. In the interim, operational status can be verified programmatically via:
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`GET /api/v1/health/ready
# Returns: { "status": "ok" | "degraded", "db": true|false, "redis": true|false }`}
        </pre>
        <p className="text-textMute">
          (TODO: Replace with public status page URL when operational dashboard is deployed.)
        </p>
      </section>
    </DocsPage>
  );
}
