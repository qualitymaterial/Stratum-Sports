import type { Metadata } from "next";

export const DOCS_LAST_UPDATED = "2026-02-28";

export type DocsNavItem = {
  href: string;
  label: string;
  description: string;
};

export const DOCS_NAV: DocsNavItem[] = [
  { href: "/docs", label: "Overview", description: "Documentation index and navigation." },
  { href: "/docs/quickstart", label: "Quickstart", description: "Initial setup and first integration steps." },
  {
    href: "/docs/authentication",
    label: "Authentication",
    description: "Auth model, token handling, and operational controls.",
  },
  {
    href: "/docs/rate-limits-and-billing",
    label: "Rate Limits & Billing",
    description: "Usage governance, overage policy, and billing controls.",
  },
  { href: "/docs/webhooks", label: "Webhooks", description: "Push delivery, signatures, and replay controls." },
  {
    href: "/docs/api-reference",
    label: "API Reference",
    description: "Endpoint catalog placeholders for implementation details.",
  },
  { href: "/docs/changelog", label: "Changelog", description: "Release notes and documented deprecations." },
  { href: "/docs/status", label: "Status", description: "Operational status and incident communication model." },
];

const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://stratumsports.com").replace(/\/$/, "");

export function createDocsMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  const canonicalUrl = `${siteUrl}${path}`;
  const fullTitle = `${title} | Stratum Docs`;
  return {
    title: fullTitle,
    description,
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      title: fullTitle,
      description,
      url: canonicalUrl,
      siteName: "Stratum",
      type: "article",
    },
  };
}
