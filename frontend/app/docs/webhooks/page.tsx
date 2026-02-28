import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

export const metadata = createDocsMetadata({
  title: "Webhooks",
  description: "Webhook delivery model, signature verification workflow, idempotency guidance, and replay protection.",
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
          Stratum delivers events through a push model. Your endpoint receives signed JSON payloads via HTTP POST and must return a 2xx acknowledgment response.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Delivery target: Your endpoint must accept HTTPS POST requests with a JSON body.</li>
          <li>Timeout: 5 seconds per delivery attempt. Endpoints that do not respond within this window are treated as failed.</li>
          <li>Retry behavior: Up to 3 retries with exponential backoff (5s initial delay, 2x multiplier). 4xx client errors are not retried.</li>
          <li>User-Agent header: <code className="rounded bg-bg px-1.5 py-0.5 text-accent">Stratum-Webhook-Engine/1.0</code></li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Signature Verification</h2>
        <p className="text-textMute">
          Each webhook payload is signed with HMAC-SHA256 using your shared secret. The signature is delivered in the <code className="rounded bg-bg px-1.5 py-0.5 text-accent">X-Stratum-Signature</code> header with a <code className="rounded bg-bg px-1.5 py-0.5 text-accent">sha256=</code> prefix.
        </p>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`Header format:
X-Stratum-Signature: sha256=<hex-encoded HMAC-SHA256 digest>

The HMAC is computed over the raw JSON request body using your webhook secret as the key.
Verify against the raw body bytes before JSON parsing.`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Node.js Verification Example</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`import crypto from "node:crypto";

const WEBHOOK_SECRET = process.env.STRATUM_WEBHOOK_SECRET ?? "";

export function verifyWebhook(rawBody, headers) {
  const header = String(headers["x-stratum-signature"] ?? "");
  const receivedSignature = header.replace("sha256=", "");

  const computedSignature = crypto
    .createHmac("sha256", WEBHOOK_SECRET)
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
        <h2 className="text-xl font-semibold">Python Verification Example</h2>
        <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
          {`import hmac
import hashlib

WEBHOOK_SECRET = "(your webhook signing secret)"

def verify_webhook(raw_body: bytes, headers: dict[str, str]) -> bool:
    header = headers.get("x-stratum-signature", "")
    received_signature = header.removeprefix("sha256=")

    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_signature, expected_signature)`}
        </pre>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Idempotency and Deduplication</h2>
        <p className="text-textMute">
          Each webhook payload includes a unique <code className="rounded bg-bg px-1.5 py-0.5 text-accent">signal_id</code> field. Use this identifier to implement idempotent processing on your end.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Store processed <code className="rounded bg-bg px-1 py-0.5">signal_id</code> values and reject duplicates before executing downstream logic.</li>
          <li>Retries may deliver the same payload multiple times. Your handler must be safe to call repeatedly with the same <code className="rounded bg-bg px-1 py-0.5">signal_id</code>.</li>
          <li>Use a durable store (database or cache with TTL) for deduplication state. In-memory sets are insufficient across process restarts.</li>
          <li>Recommended deduplication window: at least 24 hours.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Replay Protection</h2>
        <ul className="list-disc space-y-1 pl-5 text-textMute">
          <li>Each payload includes a <code className="rounded bg-bg px-1 py-0.5">created_at</code> ISO 8601 timestamp. Reject payloads older than your acceptable clock skew tolerance (recommended: 5 minutes).</li>
          <li>Combine timestamp validation with <code className="rounded bg-bg px-1 py-0.5">signal_id</code> deduplication for defense in depth.</li>
          <li>Persist replay decisions in durable storage for auditability.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Event Types</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-borderTone text-textMute">
              <tr>
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderTone/40 text-textMute">
              <tr>
                <td className="px-3 py-2 font-mono">signal.detected</td>
                <td className="px-3 py-2">A new market signal has been detected and classified.</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">signal.clv_finalized</td>
                <td className="px-3 py-2">Closing line value has been computed for a previously emitted signal.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <DocsVerifiedNote />
    </DocsPage>
  );
}
