"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { getPublicTeaserKpis, getPublicTeaserOpportunities } from "@/lib/api";
import { getStoredUser } from "@/lib/auth";
import { PublicTeaserKpisResponse, PublicTeaserOpportunity, SportKey } from "@/lib/types";

const SPORTS: Array<{ key: SportKey; label: string }> = [
  { key: "basketball_nba", label: "NBA" },
  { key: "basketball_ncaab", label: "NCAAB" },
  { key: "americanfootball_nfl", label: "NFL" },
];

const INITIAL_KPIS: PublicTeaserKpisResponse = {
  signals_in_window: 0,
  books_tracked_estimate: 0,
  pct_actionable: 0,
  pct_fresh: 0,
  updated_at: new Date(0).toISOString(),
};

function formatCommenceTime(value: string | null): string {
  if (!value) {
    return "TBD";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "UTC",
  });
}

function scoreClass(scoreStatus: PublicTeaserOpportunity["score_status"]): string {
  if (scoreStatus === "ACTIONABLE") {
    return "text-positive";
  }
  if (scoreStatus === "MONITOR") {
    return "text-accent";
  }
  return "text-negative";
}

function trackLandingEvent(name: string, payload?: Record<string, unknown>) {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new CustomEvent("stratum:landing-event", { detail: { name, ...payload } }));
}

export default function HeroLandingPage() {
  const [selectedSport, setSelectedSport] = useState<SportKey>("basketball_nba");
  const [rows, setRows] = useState<PublicTeaserOpportunity[]>([]);
  const [kpis, setKpis] = useState<PublicTeaserKpisResponse>(INITIAL_KPIS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyHint, setEmptyHint] = useState<string | null>(null);
  const [sportNotice, setSportNotice] = useState<string | null>(null);
  const [isSignedIn, setIsSignedIn] = useState(false);
  const autoSwitched = useRef(false);

  const activeSportLabel = useMemo(
    () => SPORTS.find((sport) => sport.key === selectedSport)?.label ?? "NBA",
    [selectedSport],
  );
  const noRowsState = !loading && !error && rows.length === 0;

  const loadForSport = async (sportKey: SportKey): Promise<{
    opportunities: PublicTeaserOpportunity[];
    summary: PublicTeaserKpisResponse;
  }> => {
    const [opportunities, summary] = await Promise.all([
      getPublicTeaserOpportunities({ sport_key: sportKey, limit: 5 }),
      getPublicTeaserKpis({ sport_key: sportKey, window_hours: 24 }),
    ]);
    return { opportunities, summary };
  };

  const fetchLandingData = async (sportKey: SportKey) => {
    setLoading(true);
    setError(null);
    setEmptyHint(null);

    try {
      const primary = await loadForSport(sportKey);
      if (
        sportKey === "basketball_nba" &&
        primary.opportunities.length === 0 &&
        !autoSwitched.current
      ) {
        for (const fallback of SPORTS) {
          if (fallback.key === sportKey) {
            continue;
          }
          const candidate = await loadForSport(fallback.key);
          if (candidate.opportunities.length > 0) {
            autoSwitched.current = true;
            setSelectedSport(fallback.key);
            setRows(candidate.opportunities);
            setKpis(candidate.summary);
            setSportNotice(
              `No delayed rows for NBA right now. Showing ${fallback.label} instead.`,
            );
            trackLandingEvent("landing_sport_tab_change", {
              from: "basketball_nba",
              to: fallback.key,
              reason: "auto_switch",
            });
            return;
          }
        }
        autoSwitched.current = true;
      }

      setRows(primary.opportunities);
      setKpis(primary.summary);
      setSportNotice(null);

      if (primary.opportunities.length === 0) {
        setEmptyHint("No delayed rows in this sport right now. Check another tab.");
      }
      if (primary.opportunities.length > 0) {
        trackLandingEvent("landing_teaser_row_view", {
          sport_key: sportKey,
          rows: primary.opportunities.length,
        });
      }
    } catch (err) {
      setRows([]);
      setKpis(INITIAL_KPIS);
      setError(err instanceof Error ? err.message : "Failed to load live teaser.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setIsSignedIn(Boolean(getStoredUser()));
    trackLandingEvent("landing_view", { source: "root" });
  }, []);

  useEffect(() => {
    void fetchLandingData(selectedSport);
  }, [selectedSport]);

  return (
    <main className="min-h-screen text-textMain">
      <header className="hero-shell sticky top-0 z-20 border-b border-borderTone backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <p className="text-sm font-semibold uppercase tracking-[0.28em]">STRATUM</p>
          <nav className="hidden items-center gap-6 text-sm text-textMute md:flex">
            <a href="#how-it-works" className="hover:text-accent">How It Works</a>
            <a href="#live-teaser" className="hover:text-accent">Live Teaser</a>
            <a
              href="#pricing"
              className="hover:text-accent"
              onClick={() => trackLandingEvent("landing_pricing_compare_view", { source: "nav" })}
            >
              Pricing
            </a>
            <Link
              href="/login"
              className="hover:text-accent"
              onClick={() => trackLandingEvent("landing_sign_in_click", { source: "nav" })}
            >
              Sign In
            </Link>
          </nav>
          <Link
            href="/register"
            className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-accent transition hover:bg-accent/20"
            onClick={() => trackLandingEvent("landing_cta_start_free_click", { source: "header" })}
          >
            Start Free
          </Link>
        </div>
      </header>

      <section className="hero-shell border-b border-borderTone/60">
        <div className="mx-auto grid w-full max-w-7xl gap-8 px-6 py-16 lg:grid-cols-[1.35fr_1fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-accent">Real-Time Market Intelligence</p>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight md:text-5xl">
              Read the market before the number moves.
            </h1>
            <p className="mt-5 max-w-2xl text-base text-textMute md:text-lg">
              Stratum monitors cross-book price movement, dislocation, and signal quality in real time.
              Built for disciplined market operators.
            </p>
            <p className="mt-3 max-w-2xl text-sm text-textMute">
              Execution quality and CLV process matter more than noise. Paid Intel API partner access starts at $99/month.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/register"
                className="rounded-md border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent/20"
                onClick={() => trackLandingEvent("landing_cta_start_free_click", { source: "hero" })}
              >
                Start Free
              </Link>
              <a
                href="#live-teaser"
                className="rounded-md border border-borderTone px-4 py-2 text-sm text-textMain transition hover:border-accent hover:text-accent"
              >
                Open Live Teaser
              </a>
              <Link
                href="/login"
                className="rounded-md border border-borderTone px-4 py-2 text-sm text-textMute transition hover:border-accent hover:text-accent"
                onClick={() => trackLandingEvent("landing_sign_in_click", { source: "hero" })}
              >
                Sign In
              </Link>
            </div>
            {isSignedIn && (
              <div className="mt-5 inline-flex items-center gap-2 rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-xs text-accent">
                <span>You&apos;re signed in.</span>
                <Link href="/app/dashboard" className="font-semibold underline">
                  Go to Dashboard
                </Link>
              </div>
            )}
          </div>

          <aside className="hero-panel">
            <p className="text-xs uppercase tracking-[0.22em] text-textMute">Credibility Snapshot</p>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="rounded border border-borderTone bg-panelSoft px-3 py-2">
                Multi-book coverage across major U.S. operators
              </li>
              <li className="rounded border border-borderTone bg-panelSoft px-3 py-2">
                Structured taxonomy: MOVE, KEY_CROSS, DISLOCATION, STEAM
              </li>
              <li className="rounded border border-borderTone bg-panelSoft px-3 py-2">
                Paid partner API access for private integrations ($99/month)
              </li>
            </ul>
            <p className="mt-4 text-xs text-textMute">
              Intelligence tool only. No picks and no outcome promises.
            </p>
          </aside>
        </div>
      </section>

      <section id="live-teaser" className="mx-auto w-full max-w-7xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold">Live Teaser</h2>
            <p className="text-sm text-textMute">Delayed public tape. Full real-time context is Pro.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {SPORTS.map((sport) => (
              <button
                key={sport.key}
                type="button"
                onClick={() => {
                  setSelectedSport(sport.key);
                  setSportNotice(null);
                  trackLandingEvent("landing_sport_tab_change", {
                    from: selectedSport,
                    to: sport.key,
                    reason: "manual",
                  });
                }}
                className={`rounded border px-3 py-1 text-xs font-semibold uppercase tracking-wider transition ${
                  selectedSport === sport.key
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                }`}
              >
                {sport.label}
              </button>
            ))}
          </div>
        </div>

        {sportNotice && (
          <p className="mt-4 rounded border border-borderTone bg-panel px-3 py-2 text-xs text-textMute">{sportNotice}</p>
        )}

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-[11px] uppercase tracking-wider text-textMute">Signals (24h)</p>
            <p className="mt-1 text-2xl font-semibold">{kpis.signals_in_window}</p>
          </article>
          <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-[11px] uppercase tracking-wider text-textMute">Books Tracked</p>
            <p className="mt-1 text-2xl font-semibold">{kpis.books_tracked_estimate}</p>
          </article>
          <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-[11px] uppercase tracking-wider text-textMute">Actionable Share</p>
            <p className="mt-1 text-2xl font-semibold">{noRowsState ? "—" : `${kpis.pct_actionable.toFixed(1)}%`}</p>
          </article>
          <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-[11px] uppercase tracking-wider text-textMute">Fresh Share</p>
            <p className="mt-1 text-2xl font-semibold">{noRowsState ? "—" : `${kpis.pct_fresh.toFixed(1)}%`}</p>
          </article>
        </div>
        {noRowsState && (
          <p className="mt-3 text-xs text-textMute">
            No delayed rows in the current window. This is normal between market bursts.
          </p>
        )}

        <div className="mt-6 overflow-hidden rounded-xl border border-borderTone bg-panel shadow-terminal">
          {loading ? (
            <p className="px-4 py-6 text-sm text-textMute">Loading delayed teaser for {activeSportLabel}...</p>
          ) : error ? (
            <div className="px-4 py-6">
              <p className="text-sm text-negative">{error}</p>
              <button
                type="button"
                onClick={() => void fetchLandingData(selectedSport)}
                className="mt-3 rounded border border-accent px-3 py-1.5 text-xs uppercase tracking-wider text-accent"
              >
                Retry
              </button>
            </div>
          ) : rows.length === 0 ? (
            <p className="px-4 py-6 text-sm text-textMute">{emptyHint ?? "No current teaser rows for this sport. Check another tab."}</p>
          ) : (
            <>
              <table className="hidden min-w-full text-sm md:table">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Game</th>
                    <th className="px-4 py-3">Signal</th>
                    <th className="px-4 py-3">Market</th>
                    <th className="px-4 py-3">Outcome</th>
                    <th className="px-4 py-3">Delta</th>
                    <th className="px-4 py-3">Freshness</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => (
                    <tr key={`${row.game_label ?? "game"}-${idx}`} className="border-t border-borderTone/80">
                      <td className={`px-4 py-3 font-semibold ${scoreClass(row.score_status)}`}>{row.score_status}</td>
                      <td className="px-4 py-3">
                        <p>{row.game_label ?? "Unknown matchup"}</p>
                        <p className="text-xs text-textMute">{formatCommenceTime(row.commence_time)} UTC</p>
                      </td>
                      <td className="px-4 py-3">{row.signal_type}</td>
                      <td className="px-4 py-3">{row.market}</td>
                      <td className="px-4 py-3">{row.outcome_name ?? "-"}</td>
                      <td className="px-4 py-3">{row.delta_display}</td>
                      <td className="px-4 py-3">{row.freshness_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="grid gap-3 p-3 md:hidden">
                {rows.map((row, idx) => (
                  <article key={`${row.game_label ?? "game-card"}-${idx}`} className="rounded border border-borderTone bg-panelSoft p-3">
                    <p className={`text-xs font-semibold uppercase tracking-wider ${scoreClass(row.score_status)}`}>
                      {row.score_status}
                    </p>
                    <p className="mt-2 text-sm font-medium">{row.game_label ?? "Unknown matchup"}</p>
                    <p className="text-xs text-textMute">{formatCommenceTime(row.commence_time)} UTC</p>
                    <p className="mt-2 text-xs text-textMute">
                      {row.signal_type} • {row.market} • {row.outcome_name ?? "-"}
                    </p>
                    <p className="mt-1 text-xs text-textMute">
                      Delta {row.delta_display} • {row.freshness_label}
                    </p>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      <section id="how-it-works" className="hero-shell border-y border-borderTone/60">
        <div className="mx-auto w-full max-w-7xl px-6 py-12">
          <h2 className="text-2xl font-semibold">How Stratum Works</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
              <p className="text-xs uppercase tracking-wider text-textMute">Ingest</p>
              <p className="mt-2 text-sm text-textMain">Continuously collect multi-book market snapshots by sport and market.</p>
            </article>
            <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
              <p className="text-xs uppercase tracking-wider text-textMute">Detect</p>
              <p className="mt-2 text-sm text-textMain">Apply signal rules and quality filters to isolate meaningful market movement.</p>
            </article>
            <article className="rounded-lg border border-borderTone bg-panel p-4 shadow-terminal">
              <p className="text-xs uppercase tracking-wider text-textMute">Decide</p>
              <p className="mt-2 text-sm text-textMain">Rank opportunities with execution context and CLV feedback loops.</p>
            </article>
          </div>
        </div>
      </section>

      <section id="pricing" className="mx-auto w-full max-w-7xl px-6 py-12">
        <h2 className="text-2xl font-semibold">Free vs Pro</h2>
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <article className="rounded-lg border border-borderTone bg-panel p-5 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Free</p>
            <ul className="mt-3 space-y-2 text-sm text-textMute">
              <li>Delayed market view</li>
              <li>Limited teaser rows</li>
              <li>No full actionable context</li>
            </ul>
          </article>
          <article className="rounded-lg border border-accent/40 bg-panel p-5 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-accent">Pro</p>
            <ul className="mt-3 space-y-2 text-sm text-textMain">
              <li>Full real-time signal feed</li>
              <li>Performance intelligence and recap surfaces</li>
              <li>Deeper opportunity drilldown and prioritization</li>
              <li>Intel API partner access ($99/month)</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="hero-shell border-t border-borderTone/60">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-10">
          <p className="max-w-3xl text-sm text-textMute">
            Stratum is market intelligence software, not a picks guarantee. Use disciplined bankroll and risk management.
            Developers: request API access at api-access@yourdomain.com.
          </p>
          <Link
            href="/register"
            className="rounded-md border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent/20"
            onClick={() => trackLandingEvent("landing_cta_start_free_click", { source: "footer" })}
          >
            Start Free
          </Link>
        </div>
      </section>
    </main>
  );
}
