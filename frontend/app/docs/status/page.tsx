import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Status",
  description: "Operational status communication model, incident severity, and escalation placeholders.",
  path: "/docs/status",
});

export default function DocsStatusPage() {
  return (
    <DocsPage
      title="Status"
      description="Operational status documentation for service health reporting and incident communication."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Status Endpoint</h2>
        <p className="text-textMute">(TODO: Replace with real public status page URL)</p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Incident Severity Model</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Severity 1: Broad service impairment with material delivery impact.</li>
          <li>Severity 2: Partial service degradation with constrained impact.</li>
          <li>Severity 3: Localized issue with workaround availability.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Communication Cadence</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Initial notice: (TODO: Replace with real notification SLA)</li>
          <li>Update cadence: (TODO: Replace with real update interval)</li>
          <li>Resolution summary: Published after incident closure.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
