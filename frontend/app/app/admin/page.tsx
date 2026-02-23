"use client";

import Link from "next/link";

import { LoadingState } from "@/components/LoadingState";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";

export default function AdminPage() {
  const { user, loading } = useCurrentUser(true);

  if (loading || !user) {
    return <LoadingState label="Loading admin panel..." />;
  }

  if (!user.is_admin) {
    return (
      <section className="space-y-3">
        <h1 className="text-xl font-semibold">Admin</h1>
        <div className="rounded-xl border border-borderTone bg-panel p-5 text-sm text-textMute shadow-terminal">
          <p className="text-textMain">Admin access is required for this page.</p>
          <p className="mt-2">
            Go back to{" "}
            <Link href="/app/dashboard" className="text-accent hover:underline">
              Dashboard
            </Link>
            .
          </p>
        </div>
      </section>
    );
  }

  const proAccess = hasProAccess(user);

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-textMute">Current account role and operational access scope.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Tier</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{user.tier}</p>
        </div>
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Pro Access</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{proAccess ? "Enabled" : "Disabled"}</p>
        </div>
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Admin Flag</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{user.is_admin ? "Enabled" : "Disabled"}</p>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">What Admin Can Do Today</p>
        <div className="mt-3 space-y-2 text-sm text-textMain">
          <p>1. Access all Pro-gated product surfaces and real-time feeds.</p>
          <p>2. Receive and configure Discord alert features.</p>
          <p>3. Use internal ops tooling only when paired with the ops internal token gate.</p>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">Important Notes</p>
        <div className="mt-3 space-y-2 text-sm text-textMute">
          <p>There is no full admin CRUD console in the UI yet.</p>
          <p>
            Most operational actions (deploy, backfill, promotions) are still handled through scripts and protected
            internal endpoints.
          </p>
        </div>
      </div>
    </section>
  );
}
