import type { Metadata } from "next";
import Link from "next/link";

const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://stratumsports.com").replace(/\/$/, "");
const canonicalUrl = `${siteUrl}/infrastructure`;

export const metadata: Metadata = {
  title: "Infrastructure & Methodology Disclosure | Stratum",
  description:
    "Stratum Infrastructure & Methodology Disclosure covering validation, architecture, operational controls, and institutional delivery standards.",
  alternates: {
    canonical: canonicalUrl,
  },
  openGraph: {
    title: "Infrastructure & Methodology Disclosure | Stratum",
    description:
      "Architecture, validation framework, and operational controls underlying Stratum's structured market intelligence infrastructure.",
    url: canonicalUrl,
    siteName: "Stratum",
    type: "article",
  },
};

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="rounded-lg border border-borderTone bg-panel p-6 shadow-terminal">
      <h2 className="text-xl font-semibold">{title}</h2>
      <div className="mt-4 space-y-3 text-sm leading-7 text-textMain">{children}</div>
    </section>
  );
}

export default function InfrastructurePage() {
  return (
    <main className="min-h-screen text-textMain">
      <header className="hero-shell sticky top-0 z-20 border-b border-borderTone backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.28em]">
            STRATUM
          </Link>
          <nav className="hidden items-center gap-3 text-sm text-textMute md:flex">
            <Link href="/" className="rounded px-3 py-1.5 transition hover:bg-panel hover:text-textMain">
              Home
            </Link>
            <Link
              href="/infrastructure"
              className="rounded bg-accent/15 px-3 py-1.5 text-accent transition"
              aria-current="page"
            >
              Infrastructure
            </Link>
            <Link href="/docs" className="rounded px-3 py-1.5 transition hover:bg-panel hover:text-textMain">
              Docs
            </Link>
            <Link href="/login" className="rounded px-3 py-1.5 transition hover:bg-panel hover:text-textMain">
              Sign In
            </Link>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/infrastructure"
              className="rounded bg-accent/15 px-2.5 py-1.5 text-xs uppercase tracking-wider text-accent md:hidden"
              aria-current="page"
            >
              Infrastructure
            </Link>
            <Link href="/docs" className="text-xs uppercase tracking-wider text-textMute transition hover:text-accent md:hidden">
              Docs
            </Link>
            <Link
              href="/register"
              className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-accent transition hover:bg-accent/20"
            >
              Start Free
            </Link>
          </div>
        </div>
      </header>

      <section className="hero-shell border-b border-borderTone/60">
        <div className="mx-auto w-full max-w-7xl px-6 py-12">
          <p className="text-xs uppercase tracking-[0.24em] text-accent">STRATUM</p>
          <h1 className="mt-3 text-3xl font-semibold md:text-4xl">Infrastructure &amp; Methodology Disclosure</h1>
          <p className="mt-3 text-xs text-textMute">Last updated: February 28, 2026</p>
          <div className="mt-6 max-w-4xl space-y-3 text-sm leading-7 text-textMain">
            <p>Stratum is a structured market intelligence infrastructure layer.</p>
            <p>It is not a picks service.</p>
            <p>It does not provide gambling advice.</p>
            <p>It does not guarantee outcomes.</p>
            <p>
              Stratum measures and distributes structured market data designed to evaluate probabilistic displacement
              in event markets.
            </p>
            <p>
              This document outlines the architecture, validation framework, and operational controls underlying the
              system.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-7xl px-6 py-12">
        <div className="grid gap-6">
          <Section id="core-design-principles" title="1. Core Design Principles">
            <p>Stratum is built on four foundational principles:</p>
            <ol className="list-decimal space-y-1 pl-5">
              <li>Measurement over prediction</li>
              <li>Transparency over marketing</li>
              <li>Adaptation over static modeling</li>
              <li>Infrastructure reliability over feature velocity</li>
            </ol>
            <p>Markets are adaptive systems.</p>
            <p>Edges decay.</p>
            <p>Liquidity shifts.</p>
            <p>Signal effectiveness is conditional.</p>
            <p>Stratum is designed to monitor, validate, and adapt to those dynamics.</p>
          </Section>

          <Section id="validation-framework-clv" title="2. Validation Framework: Closing Line Value (CLV)">
            <p>Stratum evaluates signals using Closing Line Value (CLV).</p>
            <p>
              CLV measures whether a signal predicts the direction of final market consensus prior to event
              commencement.
            </p>
            <p>The closing line reflects:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Aggregated capital allocation</li>
              <li>Information absorption</li>
              <li>Market maker adjustment</li>
              <li>Institutional activity</li>
            </ul>
            <p>
              If a signal consistently outperforms the closing line across statistically significant samples, it
              demonstrates informational displacement.
            </p>
            <h3 className="pt-2 text-base font-semibold">Signal Audit Process</h3>
            <p>Every signal generated by the system is:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Logged immutably</li>
              <li>Time-stamped</li>
              <li>Cross-referenced with final market consensus</li>
              <li>Automatically evaluated post-event</li>
            </ul>
            <p>No manual filtering or selective reporting is applied.</p>
            <h3 className="pt-2 text-base font-semibold">Tier Definitions</h3>
            <p>Tier B (Pro Standard)</p>
            <p>&gt; ≥ 52% positive CLV over ≥ 30 samples</p>
            <p>Tier A (Institutional)</p>
            <p>&gt; ≥ 54% positive CLV over ≥ 100 samples</p>
            <p>Tier S (Elite)</p>
            <p>&gt; ≥ 58% positive CLV over ≥ 500 samples</p>
            <p>
              Signals below minimum sample thresholds are explicitly marked as baseline building and are not rated.
            </p>
            <p>Small-sample inflation is structurally prevented.</p>
          </Section>

          <Section id="regime-classification-layer" title="3. Regime Classification Layer">
            <p>Markets operate in conditional states.</p>
            <p>
              Stratum applies a two-state Gaussian Hidden Markov Model to classify regime probability in real time.
            </p>
            <p>The model evaluates:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Line velocity</li>
              <li>Variance</li>
              <li>Movement clustering</li>
              <li>Market instability patterns</li>
            </ul>
            <p>Output:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Stable regime probability</li>
              <li>Unstable regime probability</li>
            </ul>
            <p>
              Regime classification is appended as metadata only and does not alter base signal structure. This
              ensures backward API compatibility.
            </p>
            <p>Institutional clients may condition allocation logic on regime state if desired.</p>
          </Section>

          <Section
            id="liquidity-skew-research-adaptive-thresholding"
            title="4. Liquidity Skew Research & Adaptive Thresholding"
          >
            <p>Stratum researches structural imbalance across regulated prediction markets.</p>
            <p>Liquidity skew measures directional capital imbalance between buy and sell sides.</p>
            <p>
              Backtests have demonstrated statistically significant correlation between extreme skew states and
              elevated positive CLV performance.
            </p>
            <p>However:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Static skew thresholds are not assumed permanent</li>
              <li>Percentile-based adaptive gating is preferred</li>
              <li>Forward validation precedes enforcement</li>
              <li>Shadow deployment is required before structural changes</li>
            </ul>
            <p>Edge discovery is treated as a research process, not a marketing event.</p>
          </Section>

          <Section id="ingestion-architecture-resource-management" title="5. Ingestion Architecture & Resource Management">
            <p>Stratum ingests external market data via asynchronous polling architecture.</p>
            <p>To ensure cost discipline and operational continuity:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Polling cadence adapts dynamically based on event proximity</li>
              <li>Requests are mathematically paced across 86,400 seconds per day</li>
              <li>Daily request guardrails prevent API exhaustion</li>
              <li>Graceful degradation replaces hard shutdowns</li>
            </ul>
            <p>System behavior prioritizes uptime stability over raw polling frequency.</p>
          </Section>

          <Section id="signal-filtering-noise-control" title="6. Signal Filtering & Noise Control">
            <p>To preserve signal-to-noise integrity:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Multi-book consensus minimums are enforced</li>
              <li>Structural movement thresholds are applied</li>
              <li>Dislocation cooldown periods prevent oscillation spam</li>
              <li>Historical readiness gates prevent premature rating</li>
            </ul>
            <p>Signal volume is intentionally constrained to prioritize conviction quality.</p>
          </Section>

          <Section id="delivery-architecture-cryptographic-integrity" title="7. Delivery Architecture & Cryptographic Integrity">
            <p>Institutional signals are delivered via:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Webhook push infrastructure</li>
              <li>HMAC-SHA256 cryptographic signing</li>
              <li>Encrypted transport</li>
            </ul>
            <p>
              Each payload includes a signature derived from a shared secret key. Receiving systems independently
              verify integrity prior to execution.
            </p>
            <p>This mitigates:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Man-in-the-middle modification</li>
              <li>Unauthorized payload alteration</li>
              <li>Automated execution corruption</li>
            </ul>
            <p>Data integrity is cryptographically verifiable.</p>
          </Section>

          <Section id="authentication-administrative-controls" title="8. Authentication & Administrative Controls">
            <p>Stratum enforces:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Removal of JWT tokens from URL query strings</li>
              <li>Secure first-message token validation</li>
              <li>Redis-backed replay attack prevention</li>
              <li>Mandatory time-based one-time password (TOTP) MFA</li>
              <li>Step-up authentication for privileged mutations</li>
              <li>Scoped role-based access control</li>
              <li>Automatic privilege expiration</li>
              <li>Immutable admin audit logging</li>
            </ul>
            <p>Every administrative mutation logs:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Actor identity</li>
              <li>Timestamp</li>
              <li>Before-state payload</li>
              <li>After-state payload</li>
            </ul>
            <p>Forensic traceability is preserved.</p>
          </Section>

          <Section id="versioning-api-stability" title="9. Versioning & API Stability">
            <p>Stratum maintains:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Versioned API endpoints</li>
              <li>Metadata expansion without breaking changes</li>
              <li>Documented deprecation policy</li>
              <li>Change log transparency</li>
            </ul>
            <p>Signal logic modifications are:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Shadow deployed</li>
              <li>Forward validated</li>
              <li>Monitored for decay</li>
              <li>Gradually enforced</li>
            </ul>
            <p>Breaking structural changes are avoided wherever possible.</p>
          </Section>

          <Section id="monitoring-decay-detection" title="10. Monitoring & Decay Detection">
            <p>Edge durability is continuously evaluated.</p>
            <p>Stratum monitors:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Rolling 30/60/90-day CLV</li>
              <li>Regime-conditioned performance</li>
              <li>Liquidity skew percentile drift</li>
              <li>Signal frequency shifts</li>
              <li>Drawdown clustering</li>
            </ul>
            <p>If degradation is observed:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Threshold adjustments may occur</li>
              <li>Weighting may be reduced</li>
              <li>Enforcement gates may change</li>
            </ul>
            <p>Edges are not assumed permanent.</p>
          </Section>

          <Section id="billing-usage-policy" title="11. Billing & Usage Policy">
            <p>Institutional API access operates under:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Soft request limits</li>
              <li>Transparent overage billing</li>
              <li>No free API trial policy</li>
            </ul>
            <p>The no-trial policy prevents automated scraping and dataset extraction.</p>
            <p>Operational continuity is prioritized over abrupt quota termination.</p>
          </Section>

          <Section id="intended-users" title="12. Intended Users">
            <p>Stratum is designed for:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Structured manual operators</li>
              <li>Quantitative builders</li>
              <li>Small funds</li>
              <li>Capital allocators evaluating probabilistic displacement</li>
            </ul>
            <p>Stratum is not designed for:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Guaranteed outcome seekers</li>
              <li>Emotional speculation</li>
              <li>Entertainment-based wagering</li>
            </ul>
          </Section>

          <Section id="transparency-commitment" title="13. Transparency Commitment">
            <p>Stratum publishes:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Methodology definitions</li>
              <li>Tier qualification thresholds</li>
              <li>Change logs</li>
              <li>Infrastructure disclosures</li>
            </ul>
            <p>Planned additions:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Uptime statistics</li>
              <li>Latency reporting</li>
              <li>Quarterly infrastructure summaries</li>
            </ul>
          </Section>

          <Section id="closing-statement" title="14. Closing Statement">
            <p>Markets correct inefficiency.</p>
            <p>Infrastructure survives correction.</p>
            <p>Stratum is built to measure structure in adaptive markets.</p>
          </Section>

          <section className="rounded-lg border border-borderTone bg-panel p-6 shadow-terminal">
            <h2 className="text-xl font-semibold">Contact</h2>
            <p className="mt-4 text-sm leading-7 text-textMain">
              For institutional access, integration support, or diligence requests,{" "}
              <a href="mailto:team@stratum.example" className="text-accent hover:underline">
                contact us.
              </a>
            </p>
          </section>
        </div>
      </section>
    </main>
  );
}
