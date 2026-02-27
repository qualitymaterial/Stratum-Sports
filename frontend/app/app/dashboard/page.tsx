"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { MarketSparkline } from "@/components/MarketSparkline";
import { SignalBadge } from "@/components/SignalBadge";
import { createCheckoutSession, getDashboardCards } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { getDashboardConsensusUpdate } from "@/lib/dashboardRealtime";
import { formatLine, formatMoneyline } from "@/lib/oddsFormat";
import { useOddsSocket } from "@/lib/useOddsSocket";
import { DashboardCard } from "@/lib/types";

type DashboardSportKey = "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl";

const DASHBOARD_SPORT_STORAGE_KEY = "stratum_dashboard_sport";
const DASHBOARD_SPORT_OPTIONS: Array<{ key: DashboardSportKey; label: string }> = [
  { key: "basketball_nba", label: "NBA" },
  { key: "basketball_ncaab", label: "NCAA M" },
  { key: "americanfootball_nfl", label: "NFL" },
];

function getInitialSport(): DashboardSportKey {
  if (typeof window === "undefined") {
    return "basketball_nba";
  }
  const stored = window.localStorage.getItem(DASHBOARD_SPORT_STORAGE_KEY);
  if (stored === "basketball_nba" || stored === "basketball_ncaab" || stored === "americanfootball_nfl") {
    return stored;
  }
  return "basketball_nba";
}

export default function DashboardPage() {
  const [flashing, setFlashing] = useState<Record<string, "up" | "down" | null>>({});
  const { user, loading, token } = useCurrentUser(true);
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
  const [selectedSport, setSelectedSport] = useState<DashboardSportKey>(getInitialSport);

  // Handle real-time updates
  const handleUpdate = useCallback((msg: any) => {
    setCards((prev) =>
      prev.map((card) => {
        if (card.event_id !== msg.event_id) return card;

        const update = getDashboardConsensusUpdate(card, msg);
        if (!update) {
          return card;
        }

        const newConsensus = { ...card.consensus };
        const marketKey = update.key as keyof typeof card.consensus;

        // Determine flash direction
        const prevValue = card.consensus[marketKey];
        if (prevValue !== null) {
          const key = `${card.event_id}-${marketKey}`;
          setFlashing((f) => ({ ...f, [key]: update.value > prevValue ? "up" : "down" }));
          // Clear flash after 2 seconds
          setTimeout(() => setFlashing((f) => ({ ...f, [key]: null })), 2000);
        }

        if (marketKey in newConsensus) {
          (newConsensus as any)[marketKey] = update.value;
        }

        return { ...card, consensus: newConsensus };
      })
    );
  }, []);

  const proAccess = !!user && hasProAccess(user);
  const { connected } = useOddsSocket(handleUpdate, proAccess);

  const load = async () => {
    if (!token) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const data = await getDashboardCards(token, { sport_key: selectedSport });
      setCards(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setRefreshing(false);
    }
  };

  const handleUpgradeRealtime = async () => {
    if (!token) {
      return;
    }
    setUpgrading(true);
    setError(null);
    try {
      const { url } = await createCheckoutSession(token);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start checkout");
    } finally {
      setUpgrading(false);
    }
  };

  useEffect(() => {
    if (!loading && token) {
      void load();
    }
  }, [loading, token, selectedSport]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(DASHBOARD_SPORT_STORAGE_KEY, selectedSport);
  }, [selectedSport]);

  const summary = useMemo(() => {
    const signals = cards.flatMap((card) => card.signals);
    return {
      games: cards.length,
      signals: signals.length,
      avgStrength:
        signals.length > 0
          ? Math.round(signals.reduce((acc, signal) => acc + signal.strength_score, 0) / signals.length)
          : 0,
    };
  }, [cards]);

  const selectedSportLabel =
    DASHBOARD_SPORT_OPTIONS.find((option) => option.key === selectedSport)?.label ?? "NBA";

  if (loading || !user) {
    return <LoadingState label="Loading dashboard..." />;
  }

  return (
    <section className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">Institutional Intel Feed</h1>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${!proAccess
                ? "bg-textMute/10 text-textMute border border-textMute/20"
                : connected
                  ? "bg-positive/10 text-positive border border-positive/20"
                  : "bg-textMute/10 text-textMute border border-textMute/20"
                }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${!proAccess ? "bg-textMute" : connected ? "bg-positive animate-pulse" : "bg-textMute"
                  }`}
              />
              {!proAccess ? "Realtime Pro Only" : connected ? "Live Update Active" : "Stream Offline"}
            </span>
            {!proAccess && (
              <button
                onClick={() => {
                  void handleUpgradeRealtime();
                }}
                disabled={upgrading}
                className="rounded border border-accent px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-accent transition hover:bg-accent/10 disabled:opacity-60"
              >
                {upgrading ? "Opening..." : "Upgrade to Pro ($49/mo)"}
              </button>
            )}
          </div>
          <p className="text-sm text-textMute">
            {!proAccess
              ? "Free tier data is delayed by 10 minutes. Real-time sub-second relay requires Infrastructure access."
              : "Institutional-grade real-time stream active."}
          </p>
          <div className="mt-3 inline-flex flex-wrap gap-2">
            {DASHBOARD_SPORT_OPTIONS.map((option) => {
              const active = option.key === selectedSport;
              return (
                <button
                  key={option.key}
                  onClick={() => setSelectedSport(option.key)}
                  className={`rounded border px-2.5 py-1 text-xs uppercase tracking-wider transition ${active
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                    }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
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

      <div className="grid gap-3 md:grid-cols-3">
        {/* ... (Summary stats same as before) */}
        <div className="rounded-lg border border-borderTone bg-panel p-3">
          <p className="text-xs uppercase tracking-wider text-textMute">Active Markets</p>
          <p className="mt-2 text-2xl font-semibold">{summary.games}</p>
        </div>
        <div className="rounded-lg border border-borderTone bg-panel p-3">
          <p className="text-xs uppercase tracking-wider text-textMute">Recent Signals</p>
          <p className="mt-2 text-2xl font-semibold">{summary.signals}</p>
        </div>
        <div className="rounded-lg border border-borderTone bg-panel p-3">
          <p className="text-xs uppercase tracking-wider text-textMute">Avg Strength</p>
          <p className="mt-2 text-2xl font-semibold">{summary.avgStrength}</p>
        </div>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}

      {!refreshing && !error && cards.length === 0 && (
        <div className="rounded-xl border border-borderTone bg-panel p-8 text-center shadow-terminal">
          <p className="text-sm font-medium text-textMain">No upcoming games</p>
          <p className="mt-2 text-xs text-textMute">
            {!proAccess
              ? `${selectedSportLabel} data is delayed by 10 minutes. Odds data refreshes every 60 seconds once the poller is running and an Odds API key is configured.`
              : `No qualifying ${selectedSportLabel} games in the current window. Odds data refreshes every 60 seconds when polling is active.`}
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {cards.map((card) => (
          <article
            key={card.event_id}
            className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal transition hover:border-accent/50"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium">
                  {card.away_team} @ {card.home_team}
                </p>
                <p className="text-xs text-textMute">
                  {new Date(card.commence_time).toLocaleString([], {
                    month: "short",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
              <Link
                href={`/app/games/${card.event_id}`}
                className="rounded border border-borderTone px-2 py-1 text-xs text-textMute transition hover:border-accent hover:text-accent"
              >
                Open
              </Link>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-textMute">
              <div className={`rounded border border-borderTone bg-panelSoft p-2 transition-colors duration-500 ${flashing[`${card.event_id}-spreads`] === "up" ? "animate-flash-green" :
                flashing[`${card.event_id}-spreads`] === "down" ? "animate-flash-red" : ""
                }`}>
                Spread: <span className="text-textMain">{formatLine(card.consensus.spreads)}</span>
              </div>
              <div className={`rounded border border-borderTone bg-panelSoft p-2 transition-colors duration-500 ${flashing[`${card.event_id}-totals`] === "up" ? "animate-flash-green" :
                flashing[`${card.event_id}-totals`] === "down" ? "animate-flash-red" : ""
                }`}>
                Total: <span className="text-textMain">{formatLine(card.consensus.totals)}</span>
              </div>
              <div className={`rounded border border-borderTone bg-panelSoft p-2 transition-colors duration-500 ${flashing[`${card.event_id}-h2h_home`] === "up" ? "animate-flash-green" :
                flashing[`${card.event_id}-h2h_home`] === "down" ? "animate-flash-red" : ""
                }`}>
                ML Home: <span className="text-textMain">{formatMoneyline(card.consensus.h2h_home)}</span>
              </div>
              <div className={`rounded border border-borderTone bg-panelSoft p-2 transition-colors duration-500 ${flashing[`${card.event_id}-h2h_away`] === "up" ? "animate-flash-green" :
                flashing[`${card.event_id}-h2h_away`] === "down" ? "animate-flash-red" : ""
                }`}>
                ML Away: <span className="text-textMain">{formatMoneyline(card.consensus.h2h_away)}</span>
              </div>
            </div>

            <div className="mt-4">
              <MarketSparkline values={card.sparkline} />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {card.signals.length === 0 && (
                <span className="text-xs text-textMute">No fresh signals</span>
              )}
              {card.signals.map((signal) => (
                <SignalBadge key={signal.id} signal={signal} />
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
