"use client";

import { useEffect, useState } from "react";

import {
  downloadAdminOutcomesCsv,
  downloadAdminOutcomesJson,
  getAdminOutcomesReport,
  getAdminOverview,
  getStaleAdmins,
} from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { AdminOutcomesReport, AdminOverview, StaleAdminList, User } from "@/lib/types";

type Props = { token: string; user: User };

export function AdminOverviewTab({ token, user }: Props) {
  const [days, setDays] = useState(7);
  const [cycleLimit, setCycleLimit] = useState(20);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);

  const [outcomes, setOutcomes] = useState<AdminOutcomesReport | null>(null);
  const [outcomesDays, setOutcomesDays] = useState(30);
  const [outcomesBaselineDays, setOutcomesBaselineDays] = useState(14);
  const [outcomesSportKey, setOutcomesSportKey] = useState<
    "" | "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl"
  >("");
  const [outcomesSignalType, setOutcomesSignalType] = useState("");
  const [outcomesMarket, setOutcomesMarket] = useState<"" | "spreads" | "totals" | "h2h">("");
  const [outcomesTimeBucket, setOutcomesTimeBucket] = useState<
    "" | "OPEN" | "MID" | "LATE" | "PRETIP" | "UNKNOWN"
  >("");
  const [outcomesLoading, setOutcomesLoading] = useState(false);
  const [outcomesError, setOutcomesError] = useState<string | null>(null);
  const [outcomesExportTable, setOutcomesExportTable] = useState<
    "summary" | "by_signal_type" | "by_market" | "top_filtered_reasons"
  >("summary");
  const [outcomesExporting, setOutcomesExporting] = useState<"json" | "csv" | null>(null);

  const [staleAdmins, setStaleAdmins] = useState<StaleAdminList | null>(null);
  const [staleAdminsLoading, setStaleAdminsLoading] = useState(false);

  const loadOutcomes = async (authToken: string) => {
    setOutcomesLoading(true);
    setOutcomesError(null);
    try {
      setOutcomes(
        await getAdminOutcomesReport(authToken, {
          days: outcomesDays,
          baseline_days: outcomesBaselineDays,
          sport_key: outcomesSportKey || undefined,
          signal_type: outcomesSignalType.trim() || undefined,
          market: outcomesMarket || undefined,
          time_bucket: outcomesTimeBucket || undefined,
        }),
      );
    } catch (err) {
      setOutcomes(null);
      setOutcomesError(err instanceof Error ? err.message : "Failed to load outcomes report");
    } finally {
      setOutcomesLoading(false);
    }
  };

  const runOutcomesExportJson = async () => {
    if (!token) return;
    setOutcomesExporting("json");
    setOutcomesError(null);
    try {
      await downloadAdminOutcomesJson(token, {
        days: outcomesDays,
        baseline_days: outcomesBaselineDays,
        sport_key: outcomesSportKey || undefined,
        signal_type: outcomesSignalType.trim() || undefined,
        market: outcomesMarket || undefined,
        time_bucket: outcomesTimeBucket || undefined,
      });
    } catch (err) {
      setOutcomesError(err instanceof Error ? err.message : "Failed to export JSON report");
    } finally {
      setOutcomesExporting(null);
    }
  };

  const runOutcomesExportCsv = async () => {
    if (!token) return;
    setOutcomesExporting("csv");
    setOutcomesError(null);
    try {
      await downloadAdminOutcomesCsv(token, {
        table: outcomesExportTable,
        days: outcomesDays,
        baseline_days: outcomesBaselineDays,
        sport_key: outcomesSportKey || undefined,
        signal_type: outcomesSignalType.trim() || undefined,
        market: outcomesMarket || undefined,
        time_bucket: outcomesTimeBucket || undefined,
      });
    } catch (err) {
      setOutcomesError(err instanceof Error ? err.message : "Failed to export CSV report");
    } finally {
      setOutcomesExporting(null);
    }
  };

  const loadStaleAdmins = async () => {
    if (!token) return;
    setStaleAdminsLoading(true);
    try {
      setStaleAdmins(await getStaleAdmins(token));
    } catch {
      // non-critical — silently ignore
    } finally {
      setStaleAdminsLoading(false);
    }
  };

  const load = async () => {
    if (!token || !user?.is_admin) return;
    setRefreshing(true);
    setError(null);
    try {
      setOverview(await getAdminOverview(token, { days, cycle_limit: cycleLimit }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (token && user?.is_admin) {
      void load();
      void loadStaleAdmins();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.is_admin, days, cycleLimit]);

  useEffect(() => {
    if (token && user?.is_admin) void loadOutcomes(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.is_admin, outcomesDays, outcomesBaselineDays, outcomesSportKey, outcomesSignalType, outcomesMarket, outcomesTimeBucket]);

  const proAccess = hasProAccess(user);
  const report = overview?.report ?? null;
  const ops = report?.ops;
  const reliability = report?.reliability;
  const conversion = overview?.conversion ?? null;
  const outcomesReport = outcomes;
  const recentCycles = overview?.recent_cycles ?? [];
  const topSignalTypes = Object.entries(ops?.signals_created_by_type ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const formatRate = (value: number | null | undefined) => `${((value ?? 0) * 100).toFixed(1)}%`;
  const formatDeltaRate = (value: number | null | undefined) =>
    `${(value ?? 0) >= 0 ? "+" : ""}${((value ?? 0) * 100).toFixed(1)} pp`;
  const formatSigned = (value: number | null | undefined, digits = 3) => {
    if (value == null) return "-";
    const next = Number(value);
    return `${next >= 0 ? "+" : ""}${next.toFixed(digits)}`;
  };

  return (
    <>
      <div className="grid gap-3 md:grid-cols-4">
        <label className="text-xs text-textMute">
          Report Days
          <input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(e) => setDays(Math.max(1, Math.min(30, Number(e.target.value) || 7)))}
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
            onChange={(e) => setCycleLimit(Math.max(1, Math.min(100, Number(e.target.value) || 20)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <div className="md:col-span-2 flex items-end">
          <button
            onClick={() => void load()}
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
            <p className="mt-1 text-lg font-semibold text-textMain">{ops?.total_cycles ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">Degraded {ops?.degraded_cycles ?? 0}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Avg Cycle Duration</p>
            <p className="mt-1 text-lg font-semibold text-textMain">
              {ops?.avg_cycle_duration_ms != null ? `${Math.round(ops.avg_cycle_duration_ms)} ms` : "-"}
            </p>
            <p className="mt-1 text-xs text-textMute">Signals {ops?.total_signals_created ?? 0}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Alerts</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{reliability?.alerts_sent ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">
              Failed {reliability?.alerts_failed ?? 0} ({((reliability?.alert_failure_rate ?? 0) * 100).toFixed(1)}%)
            </p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Requests Used</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{ops?.total_requests_used ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">
              Avg remaining {ops?.avg_requests_remaining != null ? ops.avg_requests_remaining.toFixed(1) : "-"}
            </p>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-textMute">Outcomes KPIs</p>
            <p className="mt-1 text-xs text-textMute">
              Outcome uses CLV-standard definition (positive when clv_line &gt; 0 or clv_prob &gt; 0).
            </p>
            <p className="text-xs text-textMute">This is prioritization/quality monitoring, not guaranteed betting outcomes.</p>
          </div>
          <button
            onClick={() => { if (token) void loadOutcomes(token); }}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
            disabled={outcomesLoading}
          >
            {outcomesLoading ? "Refreshing..." : "Refresh Outcomes"}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="text-xs text-textMute">
            Days
            <input type="number" min={7} max={90} value={outcomesDays}
              onChange={(e) => setOutcomesDays(Math.max(7, Math.min(90, Number(e.target.value) || 30)))}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain" />
          </label>
          <label className="text-xs text-textMute">
            Baseline Days
            <input type="number" min={7} max={30} value={outcomesBaselineDays}
              onChange={(e) => setOutcomesBaselineDays(Math.max(7, Math.min(30, Number(e.target.value) || 14)))}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain" />
          </label>
          <label className="text-xs text-textMute">
            Sport
            <select value={outcomesSportKey}
              onChange={(e) => setOutcomesSportKey(e.target.value as typeof outcomesSportKey)}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain">
              <option value="">all</option>
              <option value="basketball_nba">basketball_nba</option>
              <option value="basketball_ncaab">basketball_ncaab</option>
              <option value="americanfootball_nfl">americanfootball_nfl</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Signal Type
            <input value={outcomesSignalType} onChange={(e) => setOutcomesSignalType(e.target.value)} placeholder="MOVE"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain" />
          </label>
          <label className="text-xs text-textMute">
            Market
            <select value={outcomesMarket}
              onChange={(e) => setOutcomesMarket(e.target.value as typeof outcomesMarket)}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain">
              <option value="">all</option>
              <option value="spreads">spreads</option>
              <option value="totals">totals</option>
              <option value="h2h">h2h</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Time Bucket
            <select value={outcomesTimeBucket}
              onChange={(e) => setOutcomesTimeBucket(e.target.value as typeof outcomesTimeBucket)}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain">
              <option value="">all</option>
              <option value="OPEN">OPEN</option>
              <option value="MID">MID</option>
              <option value="LATE">LATE</option>
              <option value="PRETIP">PRETIP</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-xs text-textMute">
            CSV Table
            <select value={outcomesExportTable}
              onChange={(e) => setOutcomesExportTable(e.target.value as typeof outcomesExportTable)}
              className="mt-1 rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain">
              <option value="summary">summary</option>
              <option value="by_signal_type">by_signal_type</option>
              <option value="by_market">by_market</option>
              <option value="top_filtered_reasons">top_filtered_reasons</option>
            </select>
          </label>
          <button onClick={() => void runOutcomesExportJson()} disabled={outcomesExporting !== null}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60">
            {outcomesExporting === "json" ? "Exporting..." : "Export JSON"}
          </button>
          <button onClick={() => void runOutcomesExportCsv()} disabled={outcomesExporting !== null}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60">
            {outcomesExporting === "csv" ? "Exporting..." : "Export CSV"}
          </button>
        </div>

        {outcomesError && <p className="mt-3 text-sm text-negative">{outcomesError}</p>}
        {outcomesLoading && !outcomesReport && <p className="mt-3 text-sm text-textMute">Loading outcomes...</p>}

        {outcomesReport && (
          <>
            <div className="mt-4 grid gap-3 md:grid-cols-5">
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Status</p>
                <p className="mt-1 text-sm font-semibold text-textMain">{outcomesReport.status}</p>
                <p className="mt-1 text-[11px] text-textMute">{outcomesReport.status_reason}</p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">CLV Positive Rate</p>
                <p className="mt-1 text-sm font-semibold text-textMain">{formatRate(outcomesReport.kpis.clv_positive_rate)}</p>
                <p className="mt-1 text-[11px] text-textMute">Δ {formatDeltaRate(outcomesReport.delta_vs_baseline.clv_positive_rate_delta)}</p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">CLV Samples</p>
                <p className="mt-1 text-sm font-semibold text-textMain">{outcomesReport.kpis.clv_samples}</p>
                <p className="mt-1 text-[11px] text-textMute">+{outcomesReport.kpis.positive_count} / -{outcomesReport.kpis.negative_count}</p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Avg CLV</p>
                <p className="mt-1 text-sm font-semibold text-textMain">line {formatSigned(outcomesReport.kpis.avg_clv_line)}</p>
                <p className="mt-1 text-[11px] text-textMute">prob {formatSigned(outcomesReport.kpis.avg_clv_prob)}</p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Reliability</p>
                <p className="mt-1 text-sm font-semibold text-textMain">
                  Sent {formatRate(outcomesReport.kpis.sent_rate)} / Stale {formatRate(outcomesReport.kpis.stale_rate)}
                </p>
                <p className="mt-1 text-[11px] text-textMute">
                  Degraded {formatRate(outcomesReport.kpis.degraded_cycle_rate)} • Alert fail {formatRate(outcomesReport.kpis.alert_failure_rate)}
                </p>
              </div>
            </div>

            {outcomesReport.kpis.clv_samples < 30 && (
              <div className="mt-4 rounded border border-accent/30 bg-accent/5 p-2 text-xs text-textMute">
                Baseline building — {outcomesReport.kpis.clv_samples} / 30 minimum samples.
                Results will stabilize as more CLV records are computed.
              </div>
            )}

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">By Signal Type</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Signal</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                        <th className="border-b border-borderTone py-1.5">%+</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.by_signal_type.map((row) => (
                        <tr key={`signal-${row.name}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.name}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{formatRate(row.positive_rate)}</td>
                        </tr>
                      ))}
                      {outcomesReport.by_signal_type.length === 0 && (
                        <tr><td colSpan={3} className="py-2 text-textMute">No rows for current filter set.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">By Market</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Market</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                        <th className="border-b border-borderTone py-1.5">%+</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.by_market.map((row) => (
                        <tr key={`market-${row.name}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.name}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{formatRate(row.positive_rate)}</td>
                        </tr>
                      ))}
                      {outcomesReport.by_market.length === 0 && (
                        <tr><td colSpan={3} className="py-2 text-textMute">No rows for current filter set.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Top Filtered Reasons</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Reason</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.top_filtered_reasons.map((row) => (
                        <tr key={`reason-${row.reason}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.reason}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                        </tr>
                      ))}
                      {outcomesReport.top_filtered_reasons.length === 0 && (
                        <tr><td colSpan={2} className="py-2 text-textMute">No filtered reasons in this window.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {report && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Top Signal Types (Window)</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {topSignalTypes.length === 0 && <span className="text-sm text-textMute">No signal data in window.</span>}
            {topSignalTypes.map(([signalType, count]) => (
              <span key={signalType} className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-xs text-textMain">
                {signalType}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {conversion && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Conversion Funnel (Free Teaser)</p>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Teaser Views</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{conversion.teaser_views}</p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Upgrade Clicks</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{conversion.teaser_clicks}</p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">CTR</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{(conversion.click_through_rate * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Unique Users</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{conversion.unique_viewers} / {conversion.unique_clickers}</p>
              <p className="mt-1 text-xs text-textMute">viewers / clickers</p>
            </div>
          </div>
          <div className="mt-4 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Sport</th>
                  <th className="border-b border-borderTone py-2">Views</th>
                  <th className="border-b border-borderTone py-2">Clicks</th>
                  <th className="border-b border-borderTone py-2">CTR</th>
                </tr>
              </thead>
              <tbody>
                {conversion.by_sport.map((row) => (
                  <tr key={`conv-${row.sport_key}`}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.sport_key}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.teaser_views}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.teaser_clicks}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{(row.click_through_rate * 100).toFixed(1)}%</td>
                  </tr>
                ))}
                {conversion.by_sport.length === 0 && (
                  <tr><td colSpan={4} className="py-3 text-xs text-textMute">No teaser interactions recorded in this window.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {staleAdmins && staleAdmins.total > 0 && (
        <div className="rounded-xl border border-accent/30 bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-accent">
            Stale Admin Accounts ({staleAdmins.total})
          </p>
          <p className="mt-1 text-xs text-textMute">
            Admins who have not logged in within {staleAdmins.threshold_days} days.
          </p>
          <div className="mt-3 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Email</th>
                  <th className="border-b border-borderTone py-2">Role</th>
                  <th className="border-b border-borderTone py-2">Last Login</th>
                  <th className="border-b border-borderTone py-2">Days Since</th>
                </tr>
              </thead>
              <tbody>
                {staleAdmins.items.map((item) => (
                  <tr key={item.user_id}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{item.email}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{item.admin_role ?? "-"}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMute">
                      {item.last_login_at ? new Date(item.last_login_at).toLocaleDateString() : "Never"}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMute">
                      {item.days_since_login ?? "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                {recentCycles.map((cycle) => (
                  <tr key={cycle.id}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {new Date(cycle.started_at).toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.duration_ms} ms</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.snapshots_inserted ?? 0}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.signals_created_total ?? 0}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.alerts_failed ?? 0}</td>
                    <td className="border-b border-borderTone/50 py-2">
                      <span className={`rounded px-2 py-0.5 text-xs uppercase tracking-wider ${cycle.degraded ? "bg-negative/10 text-negative" : "bg-positive/10 text-positive"}`}>
                        {cycle.degraded ? "degraded" : "ok"}
                      </span>
                    </td>
                  </tr>
                ))}
                {recentCycles.length === 0 && (
                  <tr><td colSpan={6} className="py-3 text-xs text-textMute">No recent cycles in selected window.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
