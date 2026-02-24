"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import {
  createCheckoutSession,
  getBestOpportunities,
  getClvRecap,
  getClvSummary,
  getClvTeaser,
  getClvTrustScorecards,
  getDashboardCards,
  getOpportunityTeaser,
  getSignalQuality,
  getSignalLifecycleSummary,
  getSignalQualityWeeklySummary,
  trackTeaserInteraction,
} from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { applyPresetFilters } from "@/lib/performancePresets";
import {
  ClvPerformanceRow,
  ClvRecapRow,
  ClvTeaserResponse,
  ClvTrustScorecard,
  DashboardCard,
  OpportunityPoint,
  OpportunityTeaserPoint,
  SignalQualityRow,
  SignalQualityWeeklySummary,
  SignalLifecycleSummary,
  Signal,
  SportKey,
} from "@/lib/types";

const SIGNAL_OPTIONS = ["ALL", "MOVE", "KEY_CROSS", "MULTIBOOK_SYNC", "DISLOCATION", "STEAM"] as const;
const MARKET_OPTIONS = ["ALL", "spreads", "totals", "h2h"] as const;
const PRESET_OPTIONS = ["CUSTOM", "HIGH_CONFIDENCE", "LOW_NOISE", "EARLY_MOVE", "STEAM_ONLY"] as const;
type PresetOption = (typeof PRESET_OPTIONS)[number];
type RecapGrain = "day" | "week";
const PERFORMANCE_SPORT_STORAGE_KEY = "stratum_performance_sport";
const PERFORMANCE_SPORT_OPTIONS: Array<{ key: SportKey; label: string }> = [
  { key: "basketball_nba", label: "NBA" },
  { key: "basketball_ncaab", label: "NCAA M" },
  { key: "americanfootball_nfl", label: "NFL" },
];

type FreeSignalSampleRow = {
  signal: Signal;
  gameLabel: string;
  commenceTime: string;
};

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

function getInitialPerformanceSport(): SportKey {
  if (typeof window === "undefined") {
    return "basketball_nba";
  }
  const stored = window.localStorage.getItem(PERFORMANCE_SPORT_STORAGE_KEY);
  if (stored === "basketball_nba" || stored === "basketball_ncaab" || stored === "americanfootball_nfl") {
    return stored;
  }
  return "basketball_nba";
}

function resolvePerformanceSport(raw: string | null | undefined): SportKey | null {
  if (raw === "basketball_nba" || raw === "basketball_ncaab" || raw === "americanfootball_nfl") {
    return raw;
  }
  return null;
}

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

function formatOpportunityQuote(line: number | null, price: number | null): string {
  if (price == null) {
    return line != null ? formatLine(line) : "-";
  }
  return line != null ? `${formatLine(line)} (${formatAmerican(price)})` : formatAmerican(price);
}

function parseOptionalNumber(value: string | null): number | null {
  if (value == null || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveOpportunityEdge(row: OpportunityPoint): {
  value: number | null;
  label: "line" | "prob";
} {
  if (row.best_edge_line != null) {
    return { value: row.best_edge_line, label: "line" };
  }
  if (row.best_edge_prob != null) {
    return { value: row.best_edge_prob, label: "prob" };
  }
  return { value: null, label: "line" };
}

function formatOpportunityEdge(row: OpportunityPoint): string {
  const edge = resolveOpportunityEdge(row);
  if (edge.value == null) {
    return "-";
  }
  return edge.label === "prob" ? `${edge.value.toFixed(3)}p` : edge.value.toFixed(3);
}

function classifyMarketWidth(row: OpportunityPoint): "tight" | "balanced" | "wide" | "n/a" {
  if (row.market_width == null) {
    return "n/a";
  }
  if (row.market === "h2h") {
    if (row.market_width <= 0.02) {
      return "tight";
    }
    if (row.market_width >= 0.05) {
      return "wide";
    }
    return "balanced";
  }
  if (row.market_width <= 1.0) {
    return "tight";
  }
  if (row.market_width >= 2.5) {
    return "wide";
  }
  return "balanced";
}

function formatOpportunityWidth(row: OpportunityPoint): string {
  if (row.market_width == null) {
    return "-";
  }
  return row.market === "h2h" ? `${row.market_width.toFixed(3)}p` : row.market_width.toFixed(3);
}

function buildOpportunityDrilldownHref(row: OpportunityPoint): string {
  const params = new URLSearchParams();
  params.set("focus_signal_id", row.signal_id);
  params.set("focus_market", row.market);
  if (row.outcome_name) {
    params.set("focus_outcome", row.outcome_name);
  }
  return `/app/games/${row.event_id}?${params.toString()}`;
}

function buildTeaserDrilldownHref(row: OpportunityTeaserPoint): string {
  const params = new URLSearchParams();
  params.set("focus_market", row.market);
  if (row.outcome_name) {
    params.set("focus_outcome", row.outcome_name);
  }
  return `/app/games/${row.event_id}?${params.toString()}`;
}

function buildOpportunityInsight(row: OpportunityPoint): { whatChanged: string; nextStep: string } {
  const bestBook = row.best_book_key ?? "Best book";
  const delta =
    row.best_delta == null
      ? "unknown delta"
      : `${Math.abs(row.best_delta).toFixed(3)} ${
          row.delta_type === "implied_prob" ? "implied-probability points" : "line points"
        }`;
  const whatChanged = `${bestBook} is ${delta} off consensus (${formatOpportunityQuote(
    row.best_line,
    row.best_price,
  )} vs ${formatOpportunityQuote(row.consensus_line, row.consensus_price)}).`;

  if (row.opportunity_status === "actionable" && row.freshness_bucket === "fresh") {
    return {
      whatChanged,
      nextStep: "Actionable now: compare top books immediately and capture the best number.",
    };
  }
  if (row.freshness_bucket === "stale" || row.opportunity_status === "stale") {
    return {
      whatChanged,
      nextStep: "Refresh first: quote is stale, so only act if the edge still exists live.",
    };
  }
  return {
    whatChanged,
    nextStep: "Monitor: validate freshness and confirm the book still beats consensus before acting.",
  };
}

function buildOpportunityHoverText(row: OpportunityPoint): string {
  const insight = buildOpportunityInsight(row);
  const freshness = row.freshness_seconds != null ? `${Math.floor(row.freshness_seconds / 60)}m` : "unknown";
  const books = row.books_considered;
  return [
    `What changed: ${insight.whatChanged}`,
    `Freshness: ${row.freshness_bucket} (${freshness}), books=${books}`,
    `What to do: ${insight.nextStep}`,
  ].join("\n");
}

function buildQualityHoverText(row: SignalQualityRow): string {
  const dispersion = row.dispersion != null ? row.dispersion.toFixed(3) : "n/a";
  const decision =
    row.alert_decision === "sent"
      ? "Passed alert rules and was sent."
      : `Filtered by alert rules (${row.alert_reason}).`;
  const action =
    row.alert_decision === "sent"
      ? "Open game detail to compare current book quotes."
      : "Adjust filters or alert rules if this should be included.";
  return [
    `Signal: ${row.signal_type} on ${row.market} ${row.outcome_name ?? "-"}`,
    `Strength=${row.strength_score}, books=${row.books_affected}, dispersion=${dispersion}`,
    `Decision: ${decision}`,
    `Lifecycle: ${row.lifecycle_stage} (${row.lifecycle_reason})`,
    `What to do: ${action}`,
  ].join("\n");
}

function buildOpportunityScoreHoverText(row: OpportunityPoint): string {
  const components = row.score_components;
  const rankingScore = typeof row.ranking_score === "number" ? row.ranking_score : row.opportunity_score;
  const contextScore = typeof row.context_score === "number" ? row.context_score : null;
  const blendedScore = typeof row.blended_score === "number" ? row.blended_score : null;
  const scoreBasis = row.score_basis === "blended" ? "blended" : "opportunity";
  return [
    `Ranking score (${scoreBasis}) = ${rankingScore}`,
    `Opportunity score = ${row.opportunity_score}, Context score = ${contextScore ?? "-"}, Blended score = ${blendedScore ?? "-"}`,
    row.score_summary,
    `Strength=${components.strength}, Execution=${components.execution}, Delta=${components.delta}, Books=${components.books}`,
    `Freshness=${components.freshness}, CLV=${components.clv_prior}, Dispersion=${components.dispersion_penalty}, StaleCap=${components.stale_cap_penalty}`,
  ].join("\n");
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
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, loading, token } = useCurrentUser(true);
  const [selectedSport, setSelectedSport] = useState<SportKey>(getInitialPerformanceSport);
  const [days, setDays] = useState(30);
  const [signalType, setSignalType] = useState<(typeof SIGNAL_OPTIONS)[number]>("ALL");
  const [market, setMarket] = useState<(typeof MARKET_OPTIONS)[number]>("ALL");
  const [selectedPreset, setSelectedPreset] = useState<PresetOption>("HIGH_CONFIDENCE");
  const [minStrength, setMinStrength] = useState(60);
  const [minSamples, setMinSamples] = useState(10);
  const [minBooksAffected, setMinBooksAffected] = useState(1);
  const [maxDispersion, setMaxDispersion] = useState<number | null>(null);
  const [windowMinutesMax, setWindowMinutesMax] = useState<number | null>(null);
  const [minEdge, setMinEdge] = useState<number | null>(null);
  const [maxWidth, setMaxWidth] = useState<number | null>(null);
  const [includeStaleOpportunities, setIncludeStaleOpportunities] = useState(false);
  const [recapGrain, setRecapGrain] = useState<RecapGrain>("day");
  const [summaryRows, setSummaryRows] = useState<ClvPerformanceRow[]>([]);
  const [recapRows, setRecapRows] = useState<ClvRecapRow[]>([]);
  const [scorecards, setScorecards] = useState<ClvTrustScorecard[]>([]);
  const [qualityRows, setQualityRows] = useState<SignalQualityRow[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityPoint[]>([]);
  const [freeOpportunityRows, setFreeOpportunityRows] = useState<OpportunityTeaserPoint[]>([]);
  const [weeklySummary, setWeeklySummary] = useState<SignalQualityWeeklySummary | null>(null);
  const [lifecycleSummary, setLifecycleSummary] = useState<SignalLifecycleSummary | null>(null);
  const [teaser, setTeaser] = useState<ClvTeaserResponse | null>(null);
  const [freeSampleCards, setFreeSampleCards] = useState<DashboardCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
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
    const hasUrlFilters = [
      "sport_key",
      "days",
      "signal_type",
      "market",
      "preset",
      "min_strength",
      "min_samples",
      "min_books_affected",
      "max_dispersion",
      "window_minutes_max",
      "min_edge",
      "max_width",
      "include_stale",
      "recap_grain",
    ].some((key) => searchParams.has(key));

    try {
      if (hasUrlFilters) {
        const sport = resolvePerformanceSport(searchParams.get("sport_key"));
        if (sport) {
          setSelectedSport(sport);
        }
        const daysParam = Number(searchParams.get("days"));
        if (Number.isFinite(daysParam) && daysParam > 0) {
          setDays(Math.max(1, Math.min(90, daysParam)));
        }
        const signalParam = searchParams.get("signal_type");
        if (signalParam && SIGNAL_OPTIONS.includes(signalParam as (typeof SIGNAL_OPTIONS)[number])) {
          setSignalType(signalParam as (typeof SIGNAL_OPTIONS)[number]);
        }
        const marketParam = searchParams.get("market");
        if (marketParam && MARKET_OPTIONS.includes(marketParam as (typeof MARKET_OPTIONS)[number])) {
          setMarket(marketParam as (typeof MARKET_OPTIONS)[number]);
        }
        const presetParam = searchParams.get("preset");
        if (presetParam && PRESET_OPTIONS.includes(presetParam as PresetOption)) {
          setSelectedPreset(presetParam as PresetOption);
        }
        const minStrengthParam = Number(searchParams.get("min_strength"));
        if (Number.isFinite(minStrengthParam) && minStrengthParam > 0) {
          setMinStrength(Math.max(1, Math.min(100, minStrengthParam)));
        }
        const minSamplesParam = Number(searchParams.get("min_samples"));
        if (Number.isFinite(minSamplesParam) && minSamplesParam > 0) {
          setMinSamples(Math.max(1, Math.min(1000, minSamplesParam)));
        }
        const minBooksParam = Number(searchParams.get("min_books_affected"));
        if (Number.isFinite(minBooksParam) && minBooksParam > 0) {
          setMinBooksAffected(Math.max(1, Math.min(100, minBooksParam)));
        }
        const maxDispersionParam = searchParams.get("max_dispersion");
        if (maxDispersionParam == null || maxDispersionParam === "") {
          setMaxDispersion(null);
        } else {
          const parsed = Number(maxDispersionParam);
          if (Number.isFinite(parsed)) {
            setMaxDispersion(Math.max(0, parsed));
          }
        }
        const windowParam = searchParams.get("window_minutes_max");
        if (windowParam == null || windowParam === "") {
          setWindowMinutesMax(null);
        } else {
          const parsed = Number(windowParam);
          if (Number.isFinite(parsed) && parsed > 0) {
            setWindowMinutesMax(Math.max(1, Math.min(240, parsed)));
          }
        }
        const minEdgeParam = parseOptionalNumber(searchParams.get("min_edge"));
        setMinEdge(minEdgeParam == null ? null : Math.max(0, minEdgeParam));
        const maxWidthParam = parseOptionalNumber(searchParams.get("max_width"));
        setMaxWidth(maxWidthParam == null ? null : Math.max(0, maxWidthParam));
        const includeStaleParam = searchParams.get("include_stale");
        if (includeStaleParam != null) {
          setIncludeStaleOpportunities(includeStaleParam === "1" || includeStaleParam === "true");
        }
        const recapParam = searchParams.get("recap_grain");
        if (recapParam === "day" || recapParam === "week") {
          setRecapGrain(recapParam);
        }
      } else {
        const raw = window.localStorage.getItem(FILTERS_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as {
            days?: number;
            selectedSport?: SportKey;
            signalType?: (typeof SIGNAL_OPTIONS)[number];
            market?: (typeof MARKET_OPTIONS)[number];
            selectedPreset?: PresetOption;
            minStrength?: number;
            minSamples?: number;
            minBooksAffected?: number;
            maxDispersion?: number | null;
            windowMinutesMax?: number | null;
            minEdge?: number | null;
            maxWidth?: number | null;
            includeStaleOpportunities?: boolean;
            recapGrain?: RecapGrain;
          };
          if (typeof parsed.days === "number") {
            setDays(Math.max(1, Math.min(90, parsed.days)));
          }
          if (
            parsed.selectedSport === "basketball_nba" ||
            parsed.selectedSport === "basketball_ncaab" ||
            parsed.selectedSport === "americanfootball_nfl"
          ) {
            setSelectedSport(parsed.selectedSport);
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
          if (parsed.minEdge == null) {
            setMinEdge(null);
          } else if (typeof parsed.minEdge === "number" && Number.isFinite(parsed.minEdge)) {
            setMinEdge(Math.max(0, parsed.minEdge));
          }
          if (parsed.maxWidth == null) {
            setMaxWidth(null);
          } else if (typeof parsed.maxWidth === "number" && Number.isFinite(parsed.maxWidth)) {
            setMaxWidth(Math.max(0, parsed.maxWidth));
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
      }
    } catch {
      applyPreset("HIGH_CONFIDENCE");
    } finally {
      setFiltersHydrated(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!filtersHydrated || typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      FILTERS_STORAGE_KEY,
      JSON.stringify({
        days,
        selectedSport,
        signalType,
        market,
        selectedPreset,
        minStrength,
        minSamples,
        minBooksAffected,
        maxDispersion,
        windowMinutesMax,
        minEdge,
        maxWidth,
        includeStaleOpportunities,
        recapGrain,
      }),
    );
    window.localStorage.setItem(PERFORMANCE_SPORT_STORAGE_KEY, selectedSport);
  }, [
    days,
    selectedSport,
    signalType,
    market,
    selectedPreset,
    minStrength,
    minSamples,
    minBooksAffected,
    maxDispersion,
    windowMinutesMax,
    minEdge,
    maxWidth,
    includeStaleOpportunities,
    recapGrain,
    filtersHydrated,
  ]);

  useEffect(() => {
    if (!filtersHydrated) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("sport_key", selectedSport);
    params.set("days", String(days));
    params.set("signal_type", signalType);
    params.set("market", market);
    params.set("preset", selectedPreset);
    params.set("min_strength", String(minStrength));
    params.set("min_samples", String(minSamples));
    params.set("min_books_affected", String(minBooksAffected));
    params.set("max_dispersion", maxDispersion == null ? "" : String(maxDispersion));
    params.set("window_minutes_max", windowMinutesMax == null ? "" : String(windowMinutesMax));
    params.set("min_edge", minEdge == null ? "" : String(minEdge));
    params.set("max_width", maxWidth == null ? "" : String(maxWidth));
    params.set("include_stale", includeStaleOpportunities ? "1" : "0");
    params.set("recap_grain", recapGrain);
    const next = params.toString();
    const current = searchParams.toString();
    if (next !== current) {
      router.replace(`${pathname}?${next}`, { scroll: false });
    }
  }, [
    selectedSport,
    days,
    signalType,
    market,
    selectedPreset,
    minStrength,
    minSamples,
    minBooksAffected,
    maxDispersion,
    windowMinutesMax,
    minEdge,
    maxWidth,
    includeStaleOpportunities,
    recapGrain,
    filtersHydrated,
    searchParams,
    router,
    pathname,
  ]);

  const load = async () => {
    if (!token) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      if (proAccess) {
        const [
          scorecardsData,
          summaryData,
          recapData,
          weeklySummaryData,
          lifecycleSummaryData,
          qualityData,
          opportunitiesData,
        ] =
          await Promise.all([
          getClvTrustScorecards(token, {
            days,
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getClvSummary(token, {
            days,
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getClvRecap(token, {
            days,
            sport_key: selectedSport,
            grain: recapGrain,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_samples: minSamples,
            min_strength: minStrength,
          }),
          getSignalQualityWeeklySummary(token, {
            days: Math.min(30, Math.max(7, days)),
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            apply_alert_rules: true,
          }),
          getSignalLifecycleSummary(token, {
            days: Math.min(30, Math.max(7, days)),
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            apply_alert_rules: true,
          }),
          getSignalQuality(token, {
            days,
            sport_key: selectedSport,
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
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            min_edge: minEdge ?? undefined,
            max_width: maxWidth ?? undefined,
            include_stale: includeStaleOpportunities,
            limit: 10,
          }),
        ]);
        setScorecards(scorecardsData);
        setSummaryRows(summaryData);
        setRecapRows(recapData.rows);
        setWeeklySummary(weeklySummaryData);
        setLifecycleSummary(lifecycleSummaryData);
        setQualityRows(qualityData);
        setOpportunities(opportunitiesData);
        setFreeOpportunityRows([]);
        setTeaser(null);
        setFreeSampleCards([]);
      } else {
        const [teaserData, cardsData, freeOpportunityData] = await Promise.all([
          getClvTeaser(token, days, selectedSport),
          getDashboardCards(token, { sport_key: selectedSport }),
          getOpportunityTeaser(token, {
            days: Math.min(days, 7),
            sport_key: selectedSport,
            signal_type: resolvedSignalType,
            market: resolvedMarket,
            min_strength: minStrength,
            limit: 3,
          }),
        ]);
        setTeaser(teaserData);
        setFreeSampleCards(cardsData);
        setFreeOpportunityRows(freeOpportunityData);
        setSummaryRows([]);
        setRecapRows([]);
        setWeeklySummary(null);
        setLifecycleSummary(null);
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

  const handleUpgrade = async (source = "performance_upgrade_cta") => {
    if (!token) {
      return;
    }
    const trackTeaserEvent = async (
      eventName: "viewed_teaser" | "clicked_upgrade_from_teaser",
      source: string,
    ) => {
      if (!token) {
        return;
      }
      try {
        await trackTeaserInteraction(token, {
          event_name: eventName,
          source,
          sport_key: selectedSport,
        });
      } catch {
        // non-blocking
      }
    };
    setUpgrading(true);
    setError(null);
    try {
      if (!proAccess) {
        await trackTeaserEvent("clicked_upgrade_from_teaser", source);
      }
      const { url } = await createCheckoutSession(token);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start checkout");
    } finally {
      setUpgrading(false);
    }
  };

  useEffect(() => {
    if (!filtersHydrated || !token || proAccess || typeof window === "undefined") {
      return;
    }
    const key = `stratum_teaser_viewed:${selectedSport}`;
    if (window.sessionStorage.getItem(key) === "1") {
      return;
    }
    window.sessionStorage.setItem(key, "1");
    void trackTeaserInteraction(token, {
      event_name: "viewed_teaser",
      source: "performance_page",
      sport_key: selectedSport,
    }).catch(() => {});
  }, [filtersHydrated, token, proAccess, selectedSport]);

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
    selectedSport,
    days,
    signalType,
    market,
    minStrength,
    minSamples,
    minBooksAffected,
    maxDispersion,
    windowMinutesMax,
    minEdge,
    maxWidth,
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

  const freeSignalRows = useMemo<FreeSignalSampleRow[]>(() => {
    const rows: FreeSignalSampleRow[] = [];
    for (const card of freeSampleCards) {
      const gameLabel = `${card.away_team} @ ${card.home_team}`;
      for (const signal of card.signals) {
        rows.push({
          signal,
          gameLabel,
          commenceTime: card.commence_time,
        });
      }
    }
    rows.sort((a, b) => new Date(b.signal.created_at).getTime() - new Date(a.signal.created_at).getTime());
    return rows.slice(0, 14);
  }, [freeSampleCards]);

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

      <div className="grid gap-3 md:grid-cols-6">
        <label className="text-xs text-textMute">
          Sport
          <select
            value={selectedSport}
            onChange={(event) => setSelectedSport(event.target.value as SportKey)}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          >
            {PERFORMANCE_SPORT_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
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
          <button
            onClick={() => {
              void handleUpgrade("free_clv_teaser");
            }}
            disabled={upgrading}
            className="mt-3 rounded border border-accent px-3 py-1.5 text-xs uppercase tracking-wider text-accent transition hover:bg-accent/10 disabled:opacity-60"
          >
            {upgrading ? "Opening Checkout..." : "Upgrade to Unlock Live + Full Intel"}
          </button>
        </div>
      )}
      {!proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <h2 className="mb-2 text-sm uppercase tracking-wider text-textMute">Top Delayed Opportunities</h2>
          <p className="mb-3 text-xs text-textMute">
            Free tier shows delayed opportunity context so you can evaluate current board quality. Edge and width detail
            are Pro-only.
          </p>
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Game</th>
                  <th className="border-b border-borderTone py-2">Signal</th>
                  <th className="border-b border-borderTone py-2">Strength</th>
                  <th className="border-b border-borderTone py-2">Freshness</th>
                  <th className="border-b border-borderTone py-2">Edge (Pro)</th>
                  <th className="border-b border-borderTone py-2">Width (Pro)</th>
                  <th className="border-b border-borderTone py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {freeOpportunityRows.map((row) => {
                  const drilldownHref = buildTeaserDrilldownHref(row);
                  return (
                    <tr key={`${row.event_id}-${row.created_at}-${row.signal_type}-${row.market}`}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <Link href={drilldownHref} className="text-accent hover:underline">
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
                        {row.signal_type} • {row.market} • {row.outcome_name ?? "-"}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.strength_score}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <span className="capitalize">{row.freshness_bucket}</span>
                        <span className="text-xs text-textMute"> • books {row.books_considered}</span>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMute">Locked</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMute">Locked</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMute">
                        {new Date(row.created_at).toLocaleString([], {
                          month: "short",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                    </tr>
                  );
                })}
                {freeOpportunityRows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-3 text-xs text-textMute">
                      No delayed opportunities yet for the selected filters. Try widening days or setting market to
                      ALL.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <button
            onClick={() => {
              void handleUpgrade("free_delayed_opportunities");
            }}
            disabled={upgrading}
            className="mt-3 rounded border border-accent px-3 py-1.5 text-xs uppercase tracking-wider text-accent transition hover:bg-accent/10 disabled:opacity-60"
          >
            {upgrading ? "Opening Checkout..." : "Upgrade to Unlock Edge + Width"}
          </button>
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
      {!proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Free Signal Sample (Delayed)</h2>
          <p className="mb-3 text-xs text-textMute">
            You can review recent delayed signals with core trust context (books and freshness). Pro unlocks full
            CLV-grade diagnostics and actionable ranking.
          </p>
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Game</th>
                  <th className="border-b border-borderTone py-2">Signal</th>
                  <th className="border-b border-borderTone py-2">Outcome</th>
                  <th className="border-b border-borderTone py-2">Strength</th>
                  <th className="border-b border-borderTone py-2">Books</th>
                  <th className="border-b border-borderTone py-2">Freshness</th>
                </tr>
              </thead>
              <tbody>
                {freeSignalRows.map((row) => {
                  const outcome =
                    typeof row.signal.metadata?.outcome_name === "string" ? row.signal.metadata.outcome_name : "-";
                  const booksSample = Array.isArray(row.signal.metadata?.books)
                    ? (row.signal.metadata.books as unknown[]).filter((book) => typeof book === "string").slice(0, 3)
                    : [];
                  const freshnessMinutes = Math.max(0, Math.floor(row.signal.freshness_seconds / 60));
                  return (
                    <tr key={`free-sample-${row.signal.id}`}>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <div>{row.gameLabel}</div>
                        <div className="text-xs text-textMute">
                          {new Date(row.commenceTime).toLocaleString([], {
                            month: "short",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </div>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.signal.signal_type} {row.signal.direction}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{String(outcome)}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{row.signal.strength_score}</td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {row.signal.books_affected}
                        {booksSample.length > 0 && (
                          <span className="text-xs text-textMute"> ({booksSample.join(", ")})</span>
                        )}
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <span className="capitalize">{row.signal.freshness_bucket}</span>
                        <span className="text-xs text-textMute"> ({freshnessMinutes}m)</span>
                      </td>
                    </tr>
                  );
                })}
                {freeSignalRows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-3 text-xs text-textMute">
                      No delayed sample signals in the current sport/time window.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <button
            onClick={() => {
              void handleUpgrade("free_signal_sample");
            }}
            disabled={upgrading}
            className="mt-3 rounded border border-accent px-3 py-1.5 text-xs uppercase tracking-wider text-accent transition hover:bg-accent/10 disabled:opacity-60"
          >
            {upgrading ? "Opening Checkout..." : "Upgrade for Realtime + Full Filters"}
          </button>
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
            <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Alert Lifecycle</h2>
            {!lifecycleSummary && <p className="text-xs text-textMute">No lifecycle summary available yet.</p>}
            {lifecycleSummary && (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Detected</p>
                    <p className="mt-1 text-lg font-semibold text-textMain">{lifecycleSummary.total_detected}</p>
                  </div>
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Eligible</p>
                    <p className="mt-1 text-lg font-semibold text-textMain">{lifecycleSummary.eligible_signals}</p>
                  </div>
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Sent</p>
                    <p className="mt-1 text-lg font-semibold text-positive">{lifecycleSummary.sent_signals}</p>
                  </div>
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Filtered</p>
                    <p className="mt-1 text-lg font-semibold text-negative">{lifecycleSummary.filtered_signals}</p>
                  </div>
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Stale</p>
                    <p className="mt-1 text-lg font-semibold text-accent">{lifecycleSummary.stale_signals}</p>
                  </div>
                  <div className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className="text-[11px] uppercase tracking-wider text-textMute">Not Sent</p>
                    <p className="mt-1 text-lg font-semibold text-textMain">{lifecycleSummary.not_sent_signals}</p>
                  </div>
                </div>
                <div className="mt-3">
                  <p className="text-xs uppercase tracking-wider text-textMute">Top Filter Reasons</p>
                  {lifecycleSummary.top_filtered_reasons.length === 0 ? (
                    <p className="mt-1 text-xs text-textMute">No filtered signals in the selected window.</p>
                  ) : (
                    <ul className="mt-1 space-y-1 text-xs text-textMain">
                      {lifecycleSummary.top_filtered_reasons.map((item) => (
                        <li key={`${item.reason}-${item.count}`}>
                          {item.reason} <span className="text-textMute">({item.count})</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm uppercase tracking-wider text-textMute">Best Opportunities Now</h2>
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xs text-textMute">
                  Ranked by signal strength, dislocation magnitude, quote freshness, and CLV prior.
                </p>
                <label className="text-xs text-textMute">
                  Min Edge
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={minEdge ?? ""}
                    onChange={(event) => {
                      const parsed = parseOptionalNumber(event.target.value);
                      setMinEdge(parsed == null ? null : Math.max(0, parsed));
                    }}
                    placeholder="off"
                    className="ml-2 w-24 rounded border border-borderTone bg-panelSoft px-2 py-1 text-xs text-textMain"
                  />
                </label>
                <label className="text-xs text-textMute">
                  Max Width
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={maxWidth ?? ""}
                    onChange={(event) => {
                      const parsed = parseOptionalNumber(event.target.value);
                      setMaxWidth(parsed == null ? null : Math.max(0, parsed));
                    }}
                    placeholder="off"
                    className="ml-2 w-24 rounded border border-borderTone bg-panelSoft px-2 py-1 text-xs text-textMain"
                  />
                </label>
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
                    <th className="border-b border-borderTone py-2">Scores</th>
                    <th className="border-b border-borderTone py-2">Status</th>
                    <th className="border-b border-borderTone py-2">Game</th>
                    <th className="border-b border-borderTone py-2">Signal</th>
                    <th className="border-b border-borderTone py-2">Book vs Consensus</th>
                    <th className="border-b border-borderTone py-2">Edge</th>
                    <th className="border-b border-borderTone py-2">Width</th>
                    <th className="border-b border-borderTone py-2">Freshness</th>
                    <th className="border-b border-borderTone py-2">CLV Prior</th>
                    <th className="border-b border-borderTone py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.map((row) => {
                    const drilldownHref = buildOpportunityDrilldownHref(row);
                    return (
                    <tr
                      key={row.signal_id}
                      role="link"
                      tabIndex={0}
                      onClick={() => router.push(drilldownHref)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          router.push(drilldownHref);
                        }
                      }}
                      className="cursor-pointer transition hover:bg-panelSoft/40 focus-within:bg-panelSoft/40"
                    >
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        {(() => {
                          const rankingScore =
                            typeof row.ranking_score === "number" ? row.ranking_score : row.opportunity_score;
                          const contextScore = typeof row.context_score === "number" ? row.context_score : null;
                          const blendedScore = typeof row.blended_score === "number" ? row.blended_score : null;
                          const scoreBasis = row.score_basis === "blended" ? "blended" : "opportunity";
                          return (
                            <>
                              <p className="inline-flex items-center gap-1">
                                <span>{rankingScore}</span>
                                <span className="rounded border border-borderTone px-1 text-[10px] uppercase text-textMute">
                                  {scoreBasis}
                                </span>
                                <span
                                  className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-borderTone text-[10px] text-textMute"
                                  title={buildOpportunityScoreHoverText(row)}
                                  aria-label="Score breakdown"
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  ?
                                </span>
                              </p>
                              <p className="text-[11px] text-textMute">
                                Opp {row.opportunity_score} • Ctx {contextScore ?? "-"} • Blend {blendedScore ?? "-"}
                              </p>
                              <p className="text-[11px] text-textMute">{row.score_summary}</p>
                            </>
                          );
                        })()}
                      </td>
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
                        <Link
                          href={drilldownHref}
                          className="group inline-block cursor-pointer rounded-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                        >
                          <p className="text-accent group-hover:underline">
                            {row.game_label ?? `Event ${row.event_id.slice(0, 8)}`}
                          </p>
                          {row.game_commence_time && (
                            <p className="text-[11px] text-textMute group-hover:text-textMain">
                              {new Date(row.game_commence_time).toLocaleString([], {
                                month: "short",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </p>
                          )}
                        </Link>
                      </td>
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <p>
                          {row.signal_type} • {row.market} • {row.outcome_name ?? "-"}
                          <span
                            className="ml-2 inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-borderTone text-[10px] text-textMute"
                            title={buildOpportunityHoverText(row)}
                            aria-label="What this means"
                            onClick={(event) => event.stopPropagation()}
                          >
                            ?
                          </span>
                        </p>
                        <p className="text-[11px] text-textMute">
                          {row.reason_tags.join(" • ")}
                          <span className="mx-1">•</span>
                          <Link href={drilldownHref} className="text-accent hover:underline">
                            open drilldown
                          </Link>
                        </p>
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
                      <td className="border-b border-borderTone/50 py-2 text-textMain">{formatOpportunityEdge(row)}</td>
                      <td className="border-b border-borderTone/50 py-2">
                        <p className="text-textMain">{formatOpportunityWidth(row)}</p>
                        <p className="text-[11px] uppercase tracking-wider text-textMute">
                          {classifyMarketWidth(row)}
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
                    );
                  })}
                  {opportunities.length === 0 && (
                    <tr>
                      <td colSpan={10} className="py-3 text-xs text-textMute">
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
            <p className="mb-2 text-xs text-textMute">Hover `?` for "What this means" guidance.</p>
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
                    <th className="border-b border-borderTone py-2">Lifecycle</th>
                    <th className="border-b border-borderTone py-2">Alert Decision</th>
                    <th className="border-b border-borderTone py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {qualityRows.map((row) => (
                    <tr
                      key={row.id}
                      role="link"
                      tabIndex={0}
                      onClick={() => router.push(`/app/games/${row.event_id}`)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          router.push(`/app/games/${row.event_id}`);
                        }
                      }}
                      className="cursor-pointer transition hover:bg-panelSoft/40 focus-within:bg-panelSoft/40"
                    >
                      <td className="border-b border-borderTone/50 py-2 text-textMain">
                        <span className="inline-flex items-center gap-2">
                          <span>{row.signal_type}</span>
                          <span
                            className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-borderTone text-[10px] text-textMute"
                            title={buildQualityHoverText(row)}
                            aria-label="What this means"
                          >
                            ?
                          </span>
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
                            row.lifecycle_stage === "sent"
                              ? "text-positive"
                              : row.lifecycle_stage === "filtered"
                                ? "text-negative"
                                : row.lifecycle_stage === "stale"
                                  ? "text-accent"
                                  : "text-textMain"
                          }`}
                        >
                          {row.lifecycle_stage}
                        </p>
                        <p className="mt-0.5 text-[11px] text-textMute">{row.lifecycle_reason}</p>
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
                      <td colSpan={10} className="py-3 text-xs text-textMute">
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
