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
        <h2 className="text-xl font-semibold">Documentation Standards</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Public documentation only. No authentication gate.</li>
          <li>Stable, version-aware guidance for institutional integration.</li>
          <li>Explicit placeholders where implementation details are pending.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Implementation Note</h2>
        <p className="text-textMute">
          This documentation set avoids unverified endpoint definitions. Replace TODO markers with production values before external distribution.
        </p>
      </section>
    </DocsPage>
  );
}
