import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Changelog",
  description: "Public documentation change log and deprecation communication structure.",
  path: "/docs/changelog",
});

export default function DocsChangelogPage() {
  return (
    <DocsPage
      title="Changelog"
      description="This log tracks externally relevant documentation and interface changes for institutional users."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Release Logging Standard</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Document date, version, scope, and migration impact.</li>
          <li>Distinguish additive changes from behavioral modifications.</li>
          <li>Include explicit deprecation windows and retirement dates.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Entry Template</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`Date: (TODO: Replace with real date)
Version: (TODO: Replace with real version)
Category: (TODO: Replace with real category)
Summary: (TODO: Replace with real summary)
Impact: (TODO: Replace with real integration impact)
Migration Action: (TODO: Replace with real migration guidance)`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Current Entries</h2>
        <p className="text-textMute">No public entries are listed yet.</p>
        <p className="text-textMute">(TODO: Replace with real changelog entries.)</p>
      </section>
    </DocsPage>
  );
}
