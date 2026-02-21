"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { MarketSparkline } from "@/components/MarketSparkline";
import { SignalBadge } from "@/components/SignalBadge";
import { getDashboardCards } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { DashboardCard } from "@/lib/types";

export default function DashboardPage() {
  const { user, loading, token } = useCurrentUser(true);
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    if (!token) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const data = await getDashboardCards(token);
      setCards(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!loading && token) {
      void load();
    }
  }, [loading, token]);

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

  if (loading || !user) {
    return <LoadingState label="Loading dashboard..." />;
  }

  return (
    <section className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Market Dashboard</h1>
          <p className="text-sm text-textMute">
            {user.tier === "free"
              ? "Free tier data is delayed by 10 minutes."
              : "Pro tier real-time stream active."}
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

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-borderTone bg-panel p-3">
          <p className="text-xs uppercase tracking-wider text-textMute">Tracked Games</p>
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
            {user.tier === "free"
              ? "Odds data refreshes every 60 seconds once the poller is running and an Odds API key is configured."
              : "Odds data refreshes every 60 seconds. Check back once the polling worker is active."}
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
              <div className="rounded border border-borderTone bg-panelSoft p-2">
                Spread: <span className="text-textMain">{card.consensus.spreads ?? "-"}</span>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-2">
                Total: <span className="text-textMain">{card.consensus.totals ?? "-"}</span>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-2">
                ML Home: <span className="text-textMain">{card.consensus.h2h_home ?? "-"}</span>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-2">
                ML Away: <span className="text-textMain">{card.consensus.h2h_away ?? "-"}</span>
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
