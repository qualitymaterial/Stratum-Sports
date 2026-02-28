import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";

export const metadata = createDocsMetadata({
  title: "Webhooks",
  description: "Webhook delivery model, signature verification workflow, and replay protection guidance.",
  path: "/docs/webhooks",
});

export default function DocsWebhooksPage() {
  return (
    <DocsPage
      title="Webhooks"
      description="Webhook delivery supports low-latency push distribution to institutional systems with cryptographic payload verification."
    >
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Delivery Model</h2>
        <p className="text-textMute">
          Stratum delivers events through a push model. Your endpoint receives signed payloads and returns an acknowledgment response.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Delivery target: (TODO: Replace with real webhook endpoint requirements)</li>
          <li>Retry behavior: (TODO: Replace with real retry schedule and max attempts)</li>
          <li>Timeout behavior: (TODO: Replace with real timeout configuration)</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Signature Verification</h2>
        <p className="text-textMute">
          Each webhook payload is signed with HMAC-SHA256 using your shared secret. Verify against the raw request body before processing.
        </p>
        <p className="text-textMute">
          Signature header name may vary by environment or version.
          <span className="font-semibold"> (TODO: Replace with real signature header name)</span>
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Node.js Example (HMAC-SHA256)</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`import crypto from "node:crypto";

const signingSecret = process.env.STRATUM_WEBHOOK_SECRET ?? "";
const signatureHeaderName = "(TODO: Replace with real signature header name)";

export function verifyWebhook(rawBody, headers) {
  const receivedSignature = String(headers[signatureHeaderName] ?? "");
  const computedSignature = crypto
    .createHmac("sha256", signingSecret)
    .update(rawBody, "utf8")
    .digest("hex");

  const received = Buffer.from(receivedSignature, "utf8");
  const expected = Buffer.from(computedSignature, "utf8");

  if (received.length !== expected.length) {
    return false;
  }

  return crypto.timingSafeEqual(received, expected);
}`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Python Example (HMAC-SHA256)</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
{`import hmac
import hashlib

SIGNING_SECRET = "(TODO: Replace with real webhook signing secret)"
SIGNATURE_HEADER_NAME = "(TODO: Replace with real signature header name)"

def verify_webhook(raw_body: bytes, headers: dict[str, str]) -> bool:
    received_signature = headers.get(SIGNATURE_HEADER_NAME, "")
    expected_signature = hmac.new(
        SIGNING_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(received_signature, expected_signature)
`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Replay Protection Recommendation</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Require a signed timestamp field and reject stale messages.</li>
          <li>Track delivery IDs and reject duplicates within a replay window.</li>
          <li>Apply strict clock skew tolerance in verification logic.</li>
          <li>Persist replay decisions in durable storage for auditability.</li>
        </ul>
      </section>
    </DocsPage>
  );
}
