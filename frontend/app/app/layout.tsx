"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { LoadingState } from "@/components/LoadingState";
import { createCheckoutSession, createPortalSession } from "@/lib/api";
import { clearSession, useCurrentUser } from "@/lib/auth";
import { hasProAccess } from "@/lib/access";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, token } = useCurrentUser(true);

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  const handleBilling = async () => {
    if (!token || !user) {
      return;
    }

    if (hasProAccess(user)) {
      const { url } = await createPortalSession(token);
      window.location.href = url;
      return;
    }

    const { url } = await createCheckoutSession(token);
    window.location.href = url;
  };

  if (loading || !user) {
    return (
      <main className="mx-auto max-w-6xl p-6">
        <LoadingState label="Authenticating..." />
      </main>
    );
  }

  const links = [
    { href: "/app/overview", label: "Overview", proOnly: false, partnerOnly: false },
    { href: "/app/dashboard", label: "Intel Feed", proOnly: false, partnerOnly: false },
    { href: "/app/performance", label: "Analytics", proOnly: false, partnerOnly: false },
    { href: "/docs", label: "Docs", proOnly: false, partnerOnly: false },
    { href: "/app/watchlist", label: "Watchlist", proOnly: false, partnerOnly: false },
    { href: "/app/discord", label: "Discord Alerts", proOnly: true, partnerOnly: false },
  ];
  if (user.is_admin) {
    links.push({ href: "/app/admin", label: "Admin", proOnly: false, partnerOnly: false });
  }
  const proAccess = hasProAccess(user);

  return (
    <div className="min-h-screen">
      <header className="border-b border-borderTone/80 bg-panelSoft/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-6">
            <Link href="/app/dashboard" className="text-sm font-semibold uppercase tracking-[0.22em]">
              Stratum
            </Link>
            <nav className="flex gap-2 text-sm text-textMute">
              {links.map((link) => {
                const active = pathname.startsWith(link.href);
                const locked = link.proOnly && !proAccess;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    title={locked ? "Access restricted" : undefined}
                    className={`rounded px-3 py-1.5 transition ${active
                      ? "bg-accent/15 text-accent"
                      : locked
                        ? "opacity-40 hover:bg-panel hover:text-textMain"
                        : "hover:bg-panel hover:text-textMain"
                      }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {user.is_admin && (
              <Link
                href="/app/admin"
                className="rounded border border-primary px-2 py-1 font-bold uppercase tracking-widest text-primary shadow-[0_0_10px_rgba(var(--primary-rgb),0.3)] transition hover:bg-primary/10"
              >
                Admin
              </Link>
            )}
            <span
              className={`rounded border px-2 py-1 uppercase tracking-wider ${proAccess
                ? "border-accent/50 text-accent"
                : "border-borderTone text-textMute"
                }`}
            >
              {proAccess ? "pro" : user.tier}
            </span>
            <button
              onClick={() => {
                void handleBilling();
              }}
              className="rounded border border-borderTone px-2.5 py-1 text-textMute transition hover:border-accent hover:text-accent"
            >
              {proAccess ? "Billing" : "Pro ($49/mo)"}
            </button>
            <button
              onClick={logout}
              className="rounded border border-borderTone px-2.5 py-1 text-textMute transition hover:border-negative hover:text-negative"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
    </div>
  );
}
