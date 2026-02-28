import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "API Reference",
  description: "Structured API reference placeholders for endpoint, schema, and error model documentation.",
  path: "/docs/api-reference",
});

export default function DocsApiReferencePage() {
  return (
    <DocsPage
      title="API Reference"
      description="This reference is intentionally structured with placeholders until endpoint definitions are finalized for publication."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Reference Structure</h2>
        <p className="text-textMute">
          Document each endpoint with method, path, auth scope, request schema, response schema, and error semantics.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Endpoint Template</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`Operation Name: (TODO: Replace with real operation name)
Method: (TODO: Replace with real HTTP method)
Path: (TODO: Replace with real endpoint)
Authentication: (TODO: Replace with real auth scope)
Rate Limit Class: (TODO: Replace with real limit class)

Request Schema:
  (TODO: Replace with real request fields)

Response Schema:
  (TODO: Replace with real response fields)

Error Codes:
  (TODO: Replace with real error model)`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Status Codes</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>2xx: Successful request lifecycle completion.</li>
          <li>4xx: Client-originated request or authorization issue.</li>
          <li>5xx: Server-originated failure requiring retry policy evaluation.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
