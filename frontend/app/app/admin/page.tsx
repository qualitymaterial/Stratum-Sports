"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { getAdminOverview } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { AdminOverview } from "@/lib/types";

export default function AdminPage() {
  const { user, loading, token } = useCurrentUser(true);
  const [days, setDays] = useState(7);
  const [cycleLimit, setCycleLimit] = useState(20);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);

  const load = async () => {
    if (!token || !user?.is_admin) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const payload = await getAdminOverview(token, { days, cycle_limit: cycleLimit });
      setOverview(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!loading && token && user?.is_admin) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, token, user?.is_admin, days, cycleLimit]);

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
  const report = overview?.report ?? null;
  const topSignalTypes = useMemo(() => {
    const pairs = Object.entries(report?.ops.signals_created_by_type ?? {});
    return pairs.sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [report]);

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-textMute">Current account role and operational access scope.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="text-xs text-textMute">
          Report Days
          <input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(event) => setDays(Math.max(1, Math.min(30, Number(event.target.value) || 7)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Recent Cycles
          <input
            type="number"
            min={1}
            max={100}
            value={cycleLimit}
            onChange={(event) =>
              setCycleLimit(Math.max(1, Math.min(100, Number(event.target.value) || 20)))
            }
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <div className="md:col-span-2 flex items-end">
          <button
            onClick={() => {
              void load();
            }}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
          >
            {refreshing ? "Refreshing" : "Refresh Admin Data"}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}

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

      {report && (
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Cycles</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{report.ops.total_cycles}</p>
            <p className="mt-1 text-xs text-textMute">Degraded {report.ops.degraded_cycles}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Avg Cycle Duration</p>
            <p className="mt-1 text-lg font-semibold text-textMain">
              {report.ops.avg_cycle_duration_ms != null
                ? `${Math.round(report.ops.avg_cycle_duration_ms)} ms`
                : "-"}
            </p>
            <p className="mt-1 text-xs text-textMute">Signals {report.ops.total_signals_created}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Alerts</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{report.reliability.alerts_sent}</p>
            <p className="mt-1 text-xs text-textMute">
              Failed {report.reliability.alerts_failed} ({(report.reliability.alert_failure_rate * 100).toFixed(1)}%)
            </p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Requests Used</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{report.ops.total_requests_used}</p>
            <p className="mt-1 text-xs text-textMute">
              Avg remaining{" "}
              {report.ops.avg_requests_remaining != null ? report.ops.avg_requests_remaining.toFixed(1) : "-"}
            </p>
          </div>
        </div>
      )}

      {report && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Top Signal Types (Window)</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {topSignalTypes.length === 0 && <span className="text-sm text-textMute">No signal data in window.</span>}
            {topSignalTypes.map(([signalType, count]) => (
              <span
                key={signalType}
                className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-xs text-textMain"
              >
                {signalType}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {overview && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="mb-3 text-xs uppercase tracking-wider text-textMute">Recent Poll Cycles</p>
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Started</th>
                  <th className="border-b border-borderTone py-2">Duration</th>
                  <th className="border-b border-borderTone py-2">Snapshots</th>
                  <th className="border-b border-borderTone py-2">Signals</th>
                  <th className="border-b border-borderTone py-2">Alerts Failed</th>
                  <th className="border-b border-borderTone py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {overview.recent_cycles.map((cycle) => (
                  <tr key={cycle.id}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {new Date(cycle.started_at).toLocaleString([], {
                        month: "short",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.duration_ms} ms</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {cycle.snapshots_inserted ?? 0}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {cycle.signals_created_total ?? 0}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.alerts_failed ?? 0}</td>
                    <td className="border-b border-borderTone/50 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs uppercase tracking-wider ${
                          cycle.degraded ? "bg-negative/10 text-negative" : "bg-positive/10 text-positive"
                        }`}
                      >
                        {cycle.degraded ? "degraded" : "ok"}
                      </span>
                    </td>
                  </tr>
                ))}
                {overview.recent_cycles.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-3 text-xs text-textMute">
                      No recent cycles in selected window.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
