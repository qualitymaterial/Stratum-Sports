"use client";

import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { getClvSummary, getClvTeaser, getSignalQuality } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { ClvPerformanceRow, ClvTeaserResponse, SignalQualityRow } from "@/lib/types";

const SIGNAL_OPTIONS = ["ALL", "MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "STEAM"] as const;
const MARKET_OPTIONS = ["ALL", "spreads", "totals", "h2h"] as const;

export default function PerformancePage() {
  const { user, loading, token } = useCurrentUser(true);
  const [days, setDays] = useState(30);
  const [signalType, setSignalType] = useState<(typeof SIGNAL_OPTIONS)[number]>("ALL");
  const [market, setMarket] = useState<(typeof MARKET_OPTIONS)[number]>("ALL");
  const [minStrength, setMinStrength] = useState(60);
  const [minSamples, setMinSamples] = useState(10);
  const [summaryRows, setSummaryRows] = useState<ClvPerformanceRow[]>([]);
  const [qualityRows, setQualityRows] = useState<SignalQualityRow[]>([]);
  const [teaser, setTeaser] = useState<ClvTeaserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const proAccess = hasProAccess(user);
  const resolvedSignalType = signalType === "ALL" ? undefined : signalType;
  const resolvedMarket = market === "ALL" ? undefined : market;

  const load = async () => {
    if (!token) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      if (proAccess) {
        const [summary, quality] = await Promise.all([
          getClvSummary(token, {
            days,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getSignalQuality(token, {
            days,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            min_books_affected: 1,
            limit: 40,
            offset: 0,
          }),
        ]);
        setSummaryRows(summary);
        setQualityRows(quality);
        setTeaser(null);
      } else {
        const teaserData = await getClvTeaser(token, days);
        setTeaser(teaserData);
        setSummaryRows([]);
        setQualityRows([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load performance intel");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!loading && token) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, token, proAccess, days, signalType, market, minStrength, minSamples]);

  const bySignalType = useMemo(() => {
    const grouped = new Map<string, ClvPerformanceRow>();
    for (const row of summaryRows) {
      const key = row.signal_type;
      const existing = grouped.get(key);
      if (!existing) {
        grouped.set(key, { ...row });
        continue;
      }
      const totalCount = existing.count + row.count;
      const weightedPct =
        totalCount > 0
          ? ((existing.pct_positive_clv * existing.count) + (row.pct_positive_clv * row.count)) / totalCount
          : 0;
      grouped.set(key, {
        signal_type: key,
        market: "all",
        count: totalCount,
        pct_positive_clv: weightedPct,
        avg_clv_line: existing.avg_clv_line ?? row.avg_clv_line,
        avg_clv_prob: existing.avg_clv_prob ?? row.avg_clv_prob,
      });
    }
    return Array.from(grouped.values()).sort((a, b) => b.count - a.count);
  }, [summaryRows]);

  const byMarket = useMemo(() => {
    const grouped = new Map<string, ClvPerformanceRow>();
    for (const row of summaryRows) {
      const key = row.market;
      const existing = grouped.get(key);
      if (!existing) {
        grouped.set(key, { ...row });
        continue;
      }
      const totalCount = existing.count + row.count;
      const weightedPct =
        totalCount > 0
          ? ((existing.pct_positive_clv * existing.count) + (row.pct_positive_clv * row.count)) / totalCount
          : 0;
      grouped.set(key, {
        signal_type: "all",
        market: key,
        count: totalCount,
        pct_positive_clv: weightedPct,
        avg_clv_line: existing.avg_clv_line ?? row.avg_clv_line,
        avg_clv_prob: existing.avg_clv_prob ?? row.avg_clv_prob,
      });
    }
    return Array.from(grouped.values()).sort((a, b) => b.count - a.count);
  }, [summaryRows]);

  if (loading || !user) {
    return <LoadingState label="Loading performance..." />;
  }

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Performance</h1>
          <p className="text-sm text-textMute">
            {proAccess
              ? "CLV performance and signal-quality diagnostics."
              : "Free teaser view. Upgrade to unlock full CLV and quality diagnostics."}
          </p>
        </div>
        <button
          onClick={() => {
            void load();
          }}
          className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
        >
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </header>

      <div className="grid gap-3 md:grid-cols-5">
        <label className="text-xs text-textMute">
          Days
          <input
            type="number"
            min={1}
            max={90}
            value={days}
            onChange={(event) => setDays(Math.max(1, Math.min(90, Number(event.target.value) || 30)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Signal
          <select
            value={signalType}
            onChange={(event) => setSignalType(event.target.value as (typeof SIGNAL_OPTIONS)[number])}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          >
            {SIGNAL_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-textMute">
          Market
          <select
            value={market}
            onChange={(event) => setMarket(event.target.value as (typeof MARKET_OPTIONS)[number])}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          >
            {MARKET_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-textMute">
          Min Strength
          <input
            type="number"
            min={1}
            max={100}
            value={minStrength}
            onChange={(event) => setMinStrength(Math.max(1, Math.min(100, Number(event.target.value) || 60)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Min Samples
          <input
            type="number"
            min={1}
            max={1000}
            value={minSamples}
            onChange={(event) => setMinSamples(Math.max(1, Math.min(1000, Number(event.target.value) || 10)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}

      {!proAccess && teaser && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Free Teaser</p>
          <p className="mt-2 text-sm text-textMain">Samples in window: {teaser.total_records}</p>
          <div className="mt-3 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Signal</th>
                  <th className="border-b border-borderTone py-2">Market</th>
                  <th className="border-b border-borderTone py-2">Samples</th>
                  <th className="border-b border-borderTone py-2">% Positive</th>
                </tr>
              </thead>
              <tbody>
                {teaser.rows.map((row) => (
                  <tr key={`${row.signal_type}-${row.market}`}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.count}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {row.pct_positive_clv.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-textMute">
            Upgrade to Pro for full CLV diagnostics, signal quality filters, and actionable book cards.
          </p>
        </div>
      )}

      {proAccess && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
              <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">CLV by Signal Type</h2>
              <div className="overflow-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                      <th className="border-b border-borderTone py-2">Signal</th>
                      <th className="border-b border-borderTone py-2">Count</th>
                      <th className="border-b border-borderTone py-2">% Positive</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bySignalType.map((row) => (
                      <tr key={`signal-${row.signal_type}`}>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.count}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {row.pct_positive_clv.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                    {bySignalType.length === 0 && (
                      <tr>
                        <td colSpan={3} className="py-3 text-xs text-textMute">
                          No CLV samples for the selected filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
              <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">CLV by Market</h2>
              <div className="overflow-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                      <th className="border-b border-borderTone py-2">Market</th>
                      <th className="border-b border-borderTone py-2">Count</th>
                      <th className="border-b border-borderTone py-2">% Positive</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byMarket.map((row) => (
                      <tr key={`market-${row.market}`}>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.count}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {row.pct_positive_clv.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                    {byMarket.length === 0 && (
                      <tr>
                        <td colSpan={3} className="py-3 text-xs text-textMute">
                          No CLV samples for the selected filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Recent Filtered Signals</h2>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                    <th className="border-b border-borderTone py-2">Signal</th>
                    <th className="border-b border-borderTone py-2">Market</th>
                    <th className="border-b border-borderTone py-2">Outcome</th>
                    <th className="border-b border-borderTone py-2">Strength</th>
                    <th className="border-b border-borderTone py-2">Books</th>
                    <th className="border-b border-borderTone py-2">Dispersion</th>
                    <th className="border-b border-borderTone py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {qualityRows.map((row) => (
                    <tr key={row.id}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.outcome_name ?? "-"}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.strength_score}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.books_affected}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.dispersion != null ? row.dispersion.toFixed(3) : "-"}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMute">
                        {new Date(row.created_at).toLocaleString([], {
                          month: "short",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                    </tr>
                  ))}
                  {qualityRows.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-3 text-xs text-textMute">
                        No signals matched the selected quality filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
