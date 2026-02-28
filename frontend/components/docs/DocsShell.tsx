"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DOCS_NAV } from "@/app/docs/docsConfig";

function isActive(pathname: string, href: string): boolean {
  if (href === "/docs") {
    return pathname === "/docs";
  }
  return pathname.startsWith(href);
}

export default function DocsShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <main className="min-h-screen text-textMain">
      <header className="hero-shell sticky top-0 z-20 border-b border-borderTone backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.28em]">
            STRATUM
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-textMute md:flex">
            <Link href="/infrastructure" className="hover:text-accent">
              Infrastructure
            </Link>
            <Link href="/docs" className="text-accent">
              Docs
            </Link>
            <Link href="/login" className="hover:text-accent">
              Sign In
            </Link>
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/docs" className="text-xs uppercase tracking-wider text-accent md:hidden">
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

      <section className="mx-auto w-full max-w-7xl px-6 py-8">
        <div className="mb-6 md:hidden">
          <p className="text-xs uppercase tracking-[0.22em] text-textMute">Docs Sections</p>
          <nav className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {DOCS_NAV.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`shrink-0 rounded border px-3 py-1.5 text-xs uppercase tracking-wider transition ${
                    active
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="grid gap-8 md:grid-cols-[260px_1fr]">
          <aside className="hidden md:block">
            <div className="sticky top-24 rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
              <p className="text-xs uppercase tracking-[0.22em] text-textMute">Documentation</p>
              <nav className="mt-4 space-y-2">
                {DOCS_NAV.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`block rounded px-3 py-2 text-sm transition ${
                        active
                          ? "bg-accent/15 text-accent"
                          : "text-textMute hover:bg-panelSoft hover:text-textMain"
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
            </div>
          </aside>

          <div>{children}</div>
        </div>
      </section>
    </main>
  );
}
