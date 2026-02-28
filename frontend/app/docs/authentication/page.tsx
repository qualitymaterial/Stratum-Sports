import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Authentication",
  description: "Authentication model, credential handling requirements, and operational controls.",
  path: "/docs/authentication",
});

export default function DocsAuthenticationPage() {
  return (
    <DocsPage
      title="Authentication"
      description="Authentication controls are designed for institutional environments that require strict credential governance."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Authentication Model</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Transport credentials only over encrypted channels.</li>
          <li>Use server-side credential storage; never expose secrets in client-side code.</li>
          <li>Implement scoped access based on least privilege.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Request Template</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`Method: (TODO: Replace with real method)
Path: (TODO: Replace with real endpoint)
Headers:
  (TODO: Replace with real authorization header): (TODO: Replace with real auth token format)`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Credential Lifecycle</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Rotate credentials on a fixed schedule and after personnel or system changes.</li>
          <li>Maintain immutable audit logging for credential issuance and revocation events.</li>
          <li>Enforce MFA and step-up controls for privileged credential operations.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
