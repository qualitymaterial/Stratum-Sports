"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import {
  getBestOpportunities,
  getClvRecap,
  getClvSummary,
  getClvTeaser,
  getClvTrustScorecards,
  getSignalQuality,
  getSignalQualityWeeklySummary,
} from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { applyPresetFilters } from "@/lib/performancePresets";
import {
  ClvPerformanceRow,
  ClvRecapRow,
  ClvTeaserResponse,
  ClvTrustScorecard,
  OpportunityPoint,
  SignalQualityRow,
  SignalQualityWeeklySummary,
} from "@/lib/types";

const SIGNAL_OPTIONS = ["ALL", "MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "STEAM"] as const;
const MARKET_OPTIONS = ["ALL", "spreads", "totals", "h2h"] as const;
const PRESET_OPTIONS = ["CUSTOM", "HIGH_CONFIDENCE", "LOW_NOISE", "EARLY_MOVE", "STEAM_ONLY"] as const;
type PresetOption = (typeof PRESET_OPTIONS)[number];
type RecapGrain = "day" | "week";

type PresetDefinition = {
  label: string;
  description: string;
  signalType?: (typeof SIGNAL_OPTIONS)[number];
  market?: (typeof MARKET_OPTIONS)[number];
  minStrength: number;
  minSamples: number;
  minBooksAffected: number;
  maxDispersion: number | null;
  windowMinutesMax: number | null;
};

const PRESET_DEFINITIONS: Record<Exclude<PresetOption, "CUSTOM">, PresetDefinition> = {
  HIGH_CONFIDENCE: {
    label: "High Confidence",
    description: "Higher strength and book support with tighter dispersion.",
    minStrength: 75,
    minSamples: 25,
    minBooksAffected: 3,
    maxDispersion: 0.7,
    windowMinutesMax: 20,
  },
  LOW_NOISE: {
    label: "Low Noise",
    description: "Filters to steadier, lower-volatility signals.",
    minStrength: 65,
    minSamples: 20,
    minBooksAffected: 3,
    maxDispersion: 0.5,
    windowMinutesMax: 15,
  },
  EARLY_MOVE: {
    label: "Early Move",
    description: "Prioritizes fast pregame move-style signals.",
    signalType: "MOVE",
    minStrength: 60,
    minSamples: 15,
    minBooksAffected: 2,
    maxDispersion: null,
    windowMinutesMax: 10,
  },
  STEAM_ONLY: {
    label: "Steam Only",
    description: "Focuses on synchronized fast-moving steam events.",
    signalType: "STEAM",
    minStrength: 65,
    minSamples: 10,
    minBooksAffected: 4,
    maxDispersion: null,
    windowMinutesMax: 5,
  },
};

const FILTERS_STORAGE_KEY = "stratum_performance_filters_v1";

function formatRecapPeriod(periodStart: string, grain: RecapGrain): string {
  const parsed = new Date(periodStart);
  if (Number.isNaN(parsed.getTime())) {
    return periodStart;
  }
  const iso = parsed.toISOString().replace(".000Z", "Z");
  if (grain === "week") {
    return `Week of ${iso.slice(0, 10)}`;
  }
  return iso.slice(0, 10);
}

function formatAmerican(price: number | null): string {
  if (price == null) {
    return "-";
  }
  return price > 0 ? `+${price}` : `${price}`;
}

function formatLine(line: number | null): string {
  if (line == null) {
    return "-";
  }
  return Number(line).toFixed(1);
}

function buildOperatorSummary(
  weeklySummary: SignalQualityWeeklySummary | null,
  opportunities: OpportunityPoint[],
): {
  headline: string;
  detail: string;
  action: string;
  tone: "positive" | "neutral" | "negative";
} {
  const freshCount = opportunities.filter((row) => row.freshness_bucket === "fresh").length;
  const staleCount = opportunities.filter((row) => row.freshness_bucket === "stale").length;
  const actionableCount = opportunities.filter((row) => row.opportunity_status === "actionable").length;
  const monitorCount = opportunities.filter((row) => row.opportunity_status === "monitor").length;

  const sentRate = weeklySummary?.sent_rate_pct ?? null;
  const clvPositive = weeklySummary?.clv_pct_positive ?? null;
  const clvSamples = weeklySummary?.clv_samples ?? 0;

  if (opportunities.length === 0 && !weeklySummary) {
    return {
      headline: "Operator summary unavailable",
      detail: "No weekly quality snapshot or opportunities are available for the current filters.",
      action: "Widen your day window or reduce filter strictness to populate opportunities.",
      tone: "neutral",
    };
  }

  let headline = "Market quality mixed";
  let tone: "positive" | "neutral" | "negative" = "neutral";
  if ((sentRate ?? 0) >= 85 && (clvPositive ?? 0) >= 50) {
    headline = "Market quality healthy";
    tone = "positive";
  } else if ((sentRate ?? 0) < 65 || ((clvPositive ?? 0) < 42 && clvSamples >= 20)) {
    headline = "Market quality degraded";
    tone = "negative";
  }

  const detailParts = [
    `${freshCount} fresh`,
    `${monitorCount} monitor`,
    `${staleCount} stale`,
    `from ${opportunities.length} ranked opportunities`,
  ];
  if (weeklySummary) {
    detailParts.push(
      `sent rate ${weeklySummary.sent_rate_pct.toFixed(1)}%`,
      `CLV positive ${weeklySummary.clv_pct_positive.toFixed(1)}% (${weeklySummary.clv_samples} samples)`,
    );
  }

  let action = "Monitor and wait for fresher opportunities before committing.";
  if (actionableCount > 0 && freshCount > 0) {
    action = `Prioritize ${Math.min(actionableCount, freshCount)} fresh actionable setup(s), then compare top books immediately.`;
  } else if (freshCount > 0) {
    action = `Focus on ${freshCount} fresh monitor setup(s) and confirm quote freshness before acting.`;
  } else if (staleCount > 0) {
    action = "Most setups are stale; refresh quotes and avoid execution until freshness improves.";
  }

  return {
    headline,
    detail: detailParts.join(" · "),
    action,
    tone,
  };
}

export default function PerformancePage() {
  const { user, loading, token } = useCurrentUser(true);
  const [days, setDays] = useState(30);
  const [signalType, setSignalType] = useState<(typeof SIGNAL_OPTIONS)[number]>("ALL");
  const [market, setMarket] = useState<(typeof MARKET_OPTIONS)[number]>("ALL");
  const [selectedPreset, setSelectedPreset] = useState<PresetOption>("HIGH_CONFIDENCE");
  const [minStrength, setMinStrength] = useState(60);
  const [minSamples, setMinSamples] = useState(10);
  const [minBooksAffected, setMinBooksAffected] = useState(1);
  const [maxDispersion, setMaxDispersion] = useState<number | null>(null);
  const [windowMinutesMax, setWindowMinutesMax] = useState<number | null>(null);
  const [includeStaleOpportunities, setIncludeStaleOpportunities] = useState(false);
  const [recapGrain, setRecapGrain] = useState<RecapGrain>("day");
  const [summaryRows, setSummaryRows] = useState<ClvPerformanceRow[]>([]);
  const [recapRows, setRecapRows] = useState<ClvRecapRow[]>([]);
  const [scorecards, setScorecards] = useState<ClvTrustScorecard[]>([]);
  const [qualityRows, setQualityRows] = useState<SignalQualityRow[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityPoint[]>([]);
  const [weeklySummary, setWeeklySummary] = useState<SignalQualityWeeklySummary | null>(null);
  const [teaser, setTeaser] = useState<ClvTeaserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filtersHydrated, setFiltersHydrated] = useState(false);

  const proAccess = hasProAccess(user);
  const resolvedSignalType = signalType === "ALL" ? undefined : signalType;
  const resolvedMarket = market === "ALL" ? undefined : market;

  const applyPreset = (preset: PresetOption) => {
    const applied = applyPresetFilters(
      {
        selectedPreset,
        signalType,
        market,
        minStrength,
        minSamples,
        minBooksAffected,
        maxDispersion,
        windowMinutesMax,
      },
      preset,
    );
    setSelectedPreset(applied.selectedPreset as PresetOption);
    setSignalType(applied.signalType as (typeof SIGNAL_OPTIONS)[number]);
    setMarket(applied.market as (typeof MARKET_OPTIONS)[number]);
    setMinStrength(applied.minStrength);
    setMinSamples(applied.minSamples);
    setMinBooksAffected(applied.minBooksAffected);
    setMaxDispersion(applied.maxDispersion);
    setWindowMinutesMax(applied.windowMinutesMax);
  };

  const markCustom = () => setSelectedPreset("CUSTOM");

  useEffect(() => {
    if (typeof window === "undefined") {
      setFiltersHydrated(true);
      return;
    }
    try {
      const raw = window.localStorage.getItem(FILTERS_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as {
          days?: number;
          signalType?: (typeof SIGNAL_OPTIONS)[number];
          market?: (typeof MARKET_OPTIONS)[number];
          selectedPreset?: PresetOption;
          minStrength?: number;
          minSamples?: number;
          minBooksAffected?: number;
          maxDispersion?: number | null;
          windowMinutesMax?: number | null;
          includeStaleOpportunities?: boolean;
          recapGrain?: RecapGrain;
        };
        if (typeof parsed.days === "number") {
          setDays(Math.max(1, Math.min(90, parsed.days)));
        }
        if (parsed.signalType && SIGNAL_OPTIONS.includes(parsed.signalType)) {
          setSignalType(parsed.signalType);
        }
        if (parsed.market && MARKET_OPTIONS.includes(parsed.market)) {
          setMarket(parsed.market);
        }
        if (parsed.selectedPreset && PRESET_OPTIONS.includes(parsed.selectedPreset)) {
          setSelectedPreset(parsed.selectedPreset);
        }
        if (typeof parsed.minStrength === "number") {
          setMinStrength(Math.max(1, Math.min(100, parsed.minStrength)));
        }
        if (typeof parsed.minSamples === "number") {
          setMinSamples(Math.max(1, Math.min(1000, parsed.minSamples)));
        }
        if (typeof parsed.minBooksAffected === "number") {
          setMinBooksAffected(Math.max(1, Math.min(100, parsed.minBooksAffected)));
        }
        if (parsed.maxDispersion == null) {
          setMaxDispersion(null);
        } else if (typeof parsed.maxDispersion === "number" && Number.isFinite(parsed.maxDispersion)) {
          setMaxDispersion(Math.max(0, parsed.maxDispersion));
        }
        if (parsed.windowMinutesMax == null) {
          setWindowMinutesMax(null);
        } else if (typeof parsed.windowMinutesMax === "number" && Number.isFinite(parsed.windowMinutesMax)) {
          setWindowMinutesMax(Math.max(1, Math.min(240, parsed.windowMinutesMax)));
        }
        if (typeof parsed.includeStaleOpportunities === "boolean") {
          setIncludeStaleOpportunities(parsed.includeStaleOpportunities);
        }
        if (parsed.recapGrain === "day" || parsed.recapGrain === "week") {
          setRecapGrain(parsed.recapGrain);
        }
      } else {
        applyPreset("HIGH_CONFIDENCE");
      }
    } catch {
      applyPreset("HIGH_CONFIDENCE");
    } finally {
      setFiltersHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!filtersHydrated || typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      FILTERS_STORAGE_KEY,
      JSON.stringify({
        days,
        signalType,
        market,
        selectedPreset,
        minStrength,
        minSamples,
        minBooksAffected,
        maxDispersion,
        windowMinutesMax,
        includeStaleOpportunities,
        recapGrain,
      }),
    );
  }, [
    days,
    signalType,
    market,
    selectedPreset,
    minStrength,
    minSamples,
    minBooksAffected,
    maxDispersion,
    windowMinutesMax,
    includeStaleOpportunities,
    recapGrain,
    filtersHydrated,
  ]);

  const load = async () => {
    if (!token) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      if (proAccess) {
        const [scorecardsData, summaryData, recapData, weeklySummaryData, qualityData, opportunitiesData] =
          await Promise.all([
          getClvTrustScorecards(token, {
            days,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getClvSummary(token, {
            days,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getClvRecap(token, {
            days,
            grain: recapGrain,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getSignalQualityWeeklySummary(token, {
            days: Math.min(30, Math.max(7, days)),
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            apply_alert_rules: true,
          }),
          getSignalQuality(token, {
            days,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            min_books_affected: minBooksAffected,
            max_dispersion: maxDispersion ?? undefined,
            window_minutes_max: windowMinutesMax ?? undefined,
            apply_alert_rules: true,
            include_hidden: true,
            limit: 40,
            offset: 0,
          }),
          getBestOpportunities(token, {
            days: Math.min(days, 7),
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            include_stale: includeStaleOpportunities,
            limit: 10,
          }),
        ]);
        setScorecards(scorecardsData);
        setSummaryRows(summaryData);
        setRecapRows(recapData.rows);
        setWeeklySummary(weeklySummaryData);
        setQualityRows(qualityData);
        setOpportunities(opportunitiesData);
        setTeaser(null);
      } else {
        const teaserData = await getClvTeaser(token, days);
        setTeaser(teaserData);
        setSummaryRows([]);
        setRecapRows([]);
        setWeeklySummary(null);
        setScorecards([]);
        setQualityRows([]);
        setOpportunities([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load performance intel");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!filtersHydrated) {
      return;
    }
    if (!loading && token) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    loading,
    token,
    proAccess,
    days,
    signalType,
    market,
    minStrength,
    minSamples,
    minBooksAffected,
    maxDispersion,
    windowMinutesMax,
    includeStaleOpportunities,
    recapGrain,
    filtersHydrated,
  ]);

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

  const recapGroups = useMemo(() => {
    const grouped = new Map<string, ClvRecapRow[]>();
    for (const row of recapRows) {
      if (!grouped.has(row.period_start)) {
        grouped.set(row.period_start, []);
      }
      grouped.get(row.period_start)!.push(row);
    }
    return Array.from(grouped.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [recapRows]);

  const operatorSummary = useMemo(
    () => buildOperatorSummary(weeklySummary, opportunities),
    [weeklySummary, opportunities],
  );

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
            onChange={(event) => {
              setSignalType(event.target.value as (typeof SIGNAL_OPTIONS)[number]);
              markCustom();
            }}
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
            onChange={(event) => {
              setMarket(event.target.value as (typeof MARKET_OPTIONS)[number]);
              markCustom();
            }}
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
            onChange={(event) => {
              setMinStrength(Math.max(1, Math.min(100, Number(event.target.value) || 60)));
              markCustom();
            }}
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
            onChange={(event) => {
              setMinSamples(Math.max(1, Math.min(1000, Number(event.target.value) || 10)));
              markCustom();
            }}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-3 shadow-terminal">
        <div className="flex flex-wrap items-center gap-2">
          {PRESET_OPTIONS.map((preset) => {
            const isActive = selectedPreset === preset;
            return (
              <button
                key={preset}
                onClick={() => applyPreset(preset)}
                className={`rounded border px-2.5 py-1 text-xs uppercase tracking-wider transition ${
                  isActive
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                }`}
              >
                {preset === "CUSTOM" ? "Custom" : PRESET_DEFINITIONS[preset].label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-textMute">
          {selectedPreset === "CUSTOM"
            ? "Custom filter mode."
            : PRESET_DEFINITIONS[selectedPreset as Exclude<PresetOption, "CUSTOM">].description}
        </p>

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="text-xs text-textMute">
            Min Books Affected
            <input
              type="number"
              min={1}
              max={100}
              value={minBooksAffected}
              onChange={(event) => {
                setMinBooksAffected(Math.max(1, Math.min(100, Number(event.target.value) || 1)));
                markCustom();
              }}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Max Dispersion
            <input
              type="number"
              min={0}
              step={0.01}
              value={maxDispersion ?? ""}
              onChange={(event) => {
                const next = event.target.value;
                if (next === "") {
                  setMaxDispersion(null);
                } else {
                  setMaxDispersion(Math.max(0, Number(next) || 0));
                }
                markCustom();
              }}
              placeholder="off"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Max Window Minutes
            <input
              type="number"
              min={1}
              max={240}
              value={windowMinutesMax ?? ""}
              onChange={(event) => {
                const next = event.target.value;
                if (next === "") {
                  setWindowMinutesMax(null);
                } else {
                  setWindowMinutesMax(Math.max(1, Math.min(240, Number(next) || 1)));
                }
                markCustom();
              }}
              placeholder="off"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
        </div>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}

      {proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Operator Summary</p>
          <p
            className={`mt-2 text-sm font-semibold ${
              operatorSummary.tone === "positive"
                ? "text-positive"
                : operatorSummary.tone === "negative"
                  ? "text-negative"
                  : "text-accent"
            }`}
          >
            {operatorSummary.headline}
          </p>
          <p className="mt-1 text-xs text-textMute">{operatorSummary.detail}</p>
          <p className="mt-2 text-sm text-textMain">
            <span className="font-medium">Recommended next step:</span> {operatorSummary.action}
          </p>
        </div>
      )}

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
      {!proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <h2 className="mb-2 text-sm uppercase tracking-wider text-textMute">Post-Game Recap</h2>
          <p className="text-sm text-textMute">
            Post-game daily/weekly recap is available on Pro. Free tier includes teaser-level CLV aggregates only.
          </p>
        </div>
      )}
      {!proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <h2 className="mb-2 text-sm uppercase tracking-wider text-textMute">Best Opportunities Now</h2>
          <p className="text-sm text-textMute">
            Pro users get ranked opportunities with best book vs consensus, freshness, and CLV prior context.
          </p>
        </div>
      )}

      {proAccess && (
        <>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">CLV Trust Scorecards</h2>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                    <th className="border-b border-borderTone py-2">Signal</th>
                    <th className="border-b border-borderTone py-2">Market</th>
                    <th className="border-b border-borderTone py-2">Samples</th>
                    <th className="border-b border-borderTone py-2">% Positive</th>
                    <th className="border-b border-borderTone py-2">Tier</th>
                    <th className="border-b border-borderTone py-2">Score</th>
                    <th className="border-b border-borderTone py-2">Stability</th>
                  </tr>
                </thead>
                <tbody>
                  {scorecards.map((row) => (
                    <tr key={`scorecard-${row.signal_type}-${row.market}`}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.count}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.pct_positive_clv.toFixed(1)}%
                      </td>
                      <td className="border-b border-borderTone/50 py-2">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-semibold ${
                            row.confidence_tier === "A"
                              ? "bg-positive/10 text-positive"
                              : row.confidence_tier === "B"
                                ? "bg-accent/15 text-accent"
                                : "bg-textMute/20 text-textMute"
                          }`}
                        >
                          {row.confidence_tier}
                        </span>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.confidence_score}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain capitalize">
                        {row.stability_label}
                      </td>
                    </tr>
                  ))}
                  {scorecards.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-3 text-xs text-textMute">
                        No scorecards available for the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm uppercase tracking-wider text-textMute">Post-Game Recap</h2>
              <div className="flex gap-2">
                {(["day", "week"] as const).map((grain) => (
                  <button
                    key={grain}
                    onClick={() => setRecapGrain(grain)}
                    className={`rounded border px-2.5 py-1 text-xs uppercase tracking-wider transition ${
                      recapGrain === grain
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                    }`}
                  >
                    {grain}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                    <th className="border-b border-borderTone py-2">Period (UTC)</th>
                    <th className="border-b border-borderTone py-2">Signal</th>
                    <th className="border-b border-borderTone py-2">Market</th>
                    <th className="border-b border-borderTone py-2">Samples</th>
                    <th className="border-b border-borderTone py-2">% Positive</th>
                    <th className="border-b border-borderTone py-2">Avg CLV Line</th>
                    <th className="border-b border-borderTone py-2">Avg CLV Prob</th>
                  </tr>
                </thead>
                <tbody>
                  {recapGroups.flatMap(([periodStart, rows]) =>
                    rows.map((row, idx) => (
                      <tr key={`${periodStart}-${row.signal_type}-${row.market}`}>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {idx === 0 ? formatRecapPeriod(periodStart, recapGrain) : ""}
                        </td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">{row.count}</td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {row.pct_positive_clv.toFixed(1)}%
                        </td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {row.avg_clv_line != null ? row.avg_clv_line.toFixed(3) : "-"}
                        </td>
                        <td className="border-b border-borderTone/50 py-2 text-textMain">
                          {row.avg_clv_prob != null ? row.avg_clv_prob.toFixed(4) : "-"}
                        </td>
                      </tr>
                    )),
                  )}
                  {recapRows.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-3 text-xs text-textMute">
                        No post-game recap rows available for the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Your Weekly Signal Quality</h2>
            {!weeklySummary && <p className="text-xs text-textMute">No weekly summary available yet.</p>}
            {weeklySummary && (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded border border-borderTone bg-panelSoft p-3">
                  <p className="text-[11px] uppercase tracking-wider text-textMute">Signals</p>
                  <p className="mt-1 text-lg font-semibold text-textMain">{weeklySummary.total_signals}</p>
                  <p className="mt-1 text-xs text-textMute">
                    Eligible {weeklySummary.eligible_signals} / Hidden {weeklySummary.hidden_signals}
                  </p>
                </div>
                <div className="rounded border border-borderTone bg-panelSoft p-3">
                  <p className="text-[11px] uppercase tracking-wider text-textMute">Sent Rate</p>
                  <p className="mt-1 text-lg font-semibold text-textMain">{weeklySummary.sent_rate_pct.toFixed(1)}%</p>
                  <p className="mt-1 text-xs text-textMute">
                    Avg strength {weeklySummary.avg_strength != null ? weeklySummary.avg_strength.toFixed(1) : "-"}
                  </p>
                </div>
                <div className="rounded border border-borderTone bg-panelSoft p-3">
                  <p className="text-[11px] uppercase tracking-wider text-textMute">CLV Samples</p>
                  <p className="mt-1 text-lg font-semibold text-textMain">{weeklySummary.clv_samples}</p>
                  <p className="mt-1 text-xs text-textMute">
                    Positive {weeklySummary.clv_pct_positive.toFixed(1)}%
                  </p>
                </div>
                <div className="rounded border border-borderTone bg-panelSoft p-3">
                  <p className="text-[11px] uppercase tracking-wider text-textMute">Top Hidden Reason</p>
                  <p className="mt-1 text-xs text-textMain">
                    {weeklySummary.top_hidden_reason ?? "No hidden signals in window."}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm uppercase tracking-wider text-textMute">Best Opportunities Now</h2>
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xs text-textMute">
                  Ranked by signal strength, dislocation magnitude, quote freshness, and CLV prior.
                </p>
                <label className="flex items-center gap-2 text-xs text-textMute">
                  <input
                    type="checkbox"
                    checked={includeStaleOpportunities}
                    onChange={(event) => setIncludeStaleOpportunities(event.target.checked)}
                    className="h-3.5 w-3.5 rounded border border-borderTone bg-panelSoft"
                  />
                  Include stale
                </label>
              </div>
            </div>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                    <th className="border-b border-borderTone py-2">Score</th>
                    <th className="border-b border-borderTone py-2">Status</th>
                    <th className="border-b border-borderTone py-2">Game</th>
                    <th className="border-b border-borderTone py-2">Signal</th>
                    <th className="border-b border-borderTone py-2">Book vs Consensus</th>
                    <th className="border-b border-borderTone py-2">Freshness</th>
                    <th className="border-b border-borderTone py-2">CLV Prior</th>
                    <th className="border-b border-borderTone py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.map((row) => (
                    <tr key={row.signal_id}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.opportunity_score}</td>
                      <td className="border-b border-borderTone/50 py-2">
                        <span
                          className={`rounded px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${
                            row.opportunity_status === "actionable"
                              ? "bg-positive/10 text-positive"
                              : row.opportunity_status === "stale"
                                ? "bg-negative/10 text-negative"
                                : "bg-accent/10 text-accent"
                          }`}
                        >
                          {row.opportunity_status}
                        </span>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <Link href={`/app/games/${row.event_id}`} className="text-accent hover:underline">
                          {row.game_label ?? `Event ${row.event_id.slice(0, 8)}`}
                        </Link>
                        {row.game_commence_time && (
                          <p className="text-[11px] text-textMute">
                            {new Date(row.game_commence_time).toLocaleString([], {
                              month: "short",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </p>
                        )}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <p>
                          {row.signal_type} • {row.market} • {row.outcome_name ?? "-"}
                        </p>
                        <p className="text-[11px] text-textMute">{row.reason_tags.join(" • ")}</p>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <p>
                          {row.best_book_key ?? "-"}{" "}
                          {row.best_line != null
                            ? `${formatLine(row.best_line)} (${formatAmerican(row.best_price)})`
                            : formatAmerican(row.best_price)}
                        </p>
                        <p className="text-[11px] text-textMute">
                          vs{" "}
                          {row.consensus_line != null
                            ? `${formatLine(row.consensus_line)} (${formatAmerican(row.consensus_price)})`
                            : formatAmerican(row.consensus_price)}{" "}
                          • Δ {row.best_delta != null ? row.best_delta.toFixed(3) : "-"}
                        </p>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <p className="capitalize">{row.freshness_bucket}</p>
                        <p className="text-[11px] text-textMute">
                          {row.freshness_seconds != null ? `${Math.floor(row.freshness_seconds / 60)}m` : "-"} • books{" "}
                          {row.books_considered}
                        </p>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.clv_prior_pct_positive != null &&
                        row.clv_prior_samples != null &&
                        row.clv_prior_samples >= 10
                          ? `${row.clv_prior_pct_positive.toFixed(1)}% (${row.clv_prior_samples})`
                          : "N/A (n<10)"}
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
                  {opportunities.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-3 text-xs text-textMute">
                        No opportunities matched current filters. Relax min strength or widen the day window.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

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
                    <th className="border-b border-borderTone py-2">Game</th>
                    <th className="border-b border-borderTone py-2">Market</th>
                    <th className="border-b border-borderTone py-2">Outcome</th>
                    <th className="border-b border-borderTone py-2">Strength</th>
                    <th className="border-b border-borderTone py-2">Books</th>
                    <th className="border-b border-borderTone py-2">Dispersion</th>
                    <th className="border-b border-borderTone py-2">Alert Decision</th>
                    <th className="border-b border-borderTone py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {qualityRows.map((row) => (
                    <tr key={row.id}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal_type}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <Link href={`/app/games/${row.event_id}`} className="text-accent hover:underline">
                          {row.game_label ?? `Event ${row.event_id.slice(0, 8)}`}
                        </Link>
                        {row.game_commence_time && (
                          <p className="text-[11px] text-textMute">
                            {new Date(row.game_commence_time).toLocaleString([], {
                              month: "short",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </p>
                        )}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.market}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.outcome_name ?? "-"}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.strength_score}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.books_affected}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.dispersion != null ? row.dispersion.toFixed(3) : "-"}
                      </td>
                      <td className="border-b border-borderTone/50 py-2">
                        <p
                          className={`text-xs font-semibold uppercase tracking-wider ${
                            row.alert_decision === "sent" ? "text-positive" : "text-negative"
                          }`}
                        >
                          {row.alert_decision}
                        </p>
                        <p className="mt-0.5 text-[11px] text-textMute">{row.alert_reason}</p>
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
                      <td colSpan={9} className="py-3 text-xs text-textMute">
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
