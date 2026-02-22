"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { MovementChart } from "@/components/MovementChart";
import { SignalBadge } from "@/components/SignalBadge";
import { getActionableBookCardsBatch, getGameDetail } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { getApiBaseUrl } from "@/lib/apiClient";
import { useCurrentUser } from "@/lib/auth";
import { ActionableBookCard, GameDetail } from "@/lib/types";

const API_BASE = getApiBaseUrl();

export default function GameDetailPage() {
  const params = useParams<{ event_id: string }>();
  const eventId = params.event_id;
  const { user, loading, token } = useCurrentUser(true);

  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [actionableCards, setActionableCards] = useState<Record<string, ActionableBookCard | null>>({});
  const [actionableLoading, setActionableLoading] = useState(false);

  const load = async () => {
    if (!token || !eventId) {
      return;
    }
    setError(null);
    try {
      const response = await getGameDetail(eventId, token);
      setDetail(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load game detail");
    }
  };

  useEffect(() => {
    if (!loading && token && eventId) {
      void load();
    }
  }, [loading, token, eventId]);

  const downloadCsv = async (market: "spreads" | "totals" | "h2h") => {
    if (!token || !eventId) {
      return;
    }
    setDownloading(true);
    try {
      const response = await fetch(`${API_BASE}/games/${eventId}/export.csv?market=${market}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "CSV export failed");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${eventId}-${market}.csv`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "CSV export failed");
    } finally {
      setDownloading(false);
    }
  };

  const groupedOdds = useMemo(() => {
    if (!detail) {
      return [];
    }
    return [...detail.odds].sort((a, b) => {
      const left = `${a.sportsbook_key}-${a.market}-${a.outcome_name}`;
      const right = `${b.sportsbook_key}-${b.market}-${b.outcome_name}`;
      return left.localeCompare(right);
    });
  }, [detail]);

  const proAccess = hasProAccess(user);
  const actionableSignalIds = useMemo(
    () => detail?.signals.slice(0, 6).map((signal) => signal.id) ?? [],
    [detail],
  );
  const actionableSignalIdSet = useMemo(() => new Set(actionableSignalIds), [actionableSignalIds]);

  useEffect(() => {
    if (!proAccess || !token || !eventId || actionableSignalIds.length === 0) {
      setActionableCards({});
      return;
    }

    let cancelled = false;
    const run = async () => {
      setActionableLoading(true);
      try {
        const cards = await getActionableBookCardsBatch(token, eventId, actionableSignalIds);
        if (cancelled) {
          return;
        }
        const map: Record<string, ActionableBookCard | null> = Object.fromEntries(
          cards.map((card) => [card.signal_id, card] as const),
        );
        for (const signalId of actionableSignalIds) {
          if (!(signalId in map)) {
            map[signalId] = null;
          }
        }
        setActionableCards(map);
      } catch {
        if (!cancelled) {
          const fallback = Object.fromEntries(actionableSignalIds.map((signalId) => [signalId, null] as const));
          setActionableCards(fallback);
        }
      } finally {
        if (!cancelled) {
          setActionableLoading(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [actionableSignalIds, eventId, proAccess, token]);

  if (loading || !user) {
    return <LoadingState label="Loading game..." />;
  }

  if (!detail) {
    return <LoadingState label={error ?? "Loading game detail..."} />;
  }

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            {detail.away_team} @ {detail.home_team}
          </h1>
          <p className="text-sm text-textMute">
            {new Date(detail.commence_time).toLocaleString([], {
              month: "short",
              day: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>

        <div className="flex gap-2">
          {proAccess ? (
            <>
              <button
                onClick={() => {
                  void downloadCsv("spreads");
                }}
                className="rounded border border-borderTone px-3 py-1 text-xs text-textMute hover:border-accent hover:text-accent"
              >
                {downloading ? "Exporting" : "Export Spread CSV"}
              </button>
              <button
                onClick={() => {
                  void downloadCsv("totals");
                }}
                className="rounded border border-borderTone px-3 py-1 text-xs text-textMute hover:border-accent hover:text-accent"
              >
                Export Total CSV
              </button>
            </>
          ) : (
            <span className="rounded border border-borderTone px-3 py-1 text-xs text-textMute">
              CSV export is Pro only
            </span>
          )}
        </div>
      </header>

      {error && <p className="text-sm text-negative">{error}</p>}

      <MovementChart points={detail.chart_series} />

      <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Latest Odds by Book</h2>
        <div className="max-h-[360px] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                <th className="border-b border-borderTone py-2">Book</th>
                <th className="border-b border-borderTone py-2">Market</th>
                <th className="border-b border-borderTone py-2">Outcome</th>
                <th className="border-b border-borderTone py-2">Line</th>
                <th className="border-b border-borderTone py-2">Price</th>
                <th className="border-b border-borderTone py-2">Fetched</th>
              </tr>
            </thead>
            <tbody>
              {groupedOdds.map((row, idx) => (
                <tr key={`${row.sportsbook_key}-${row.market}-${row.outcome_name}-${idx}`}>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">{row.sportsbook_key}</td>
                  <td className="border-b border-borderTone/50 py-2 text-textMute">{row.market}</td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">{row.outcome_name}</td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">{row.line ?? "-"}</td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">{row.price}</td>
                  <td className="border-b border-borderTone/50 py-2 text-textMute">
                    {new Date(row.fetched_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Signals</h2>
        <div className="space-y-2">
          {detail.signals.length === 0 && <p className="text-sm text-textMute">No signals recorded yet.</p>}
          {detail.signals.slice(0, 40).map((signal) => {
            const outcome =
              typeof signal.metadata?.outcome_name === "string" ? String(signal.metadata.outcome_name) : "-";
            const actionable = actionableCards[signal.id];
            const hasActionableSlot = actionableSignalIdSet.has(signal.id);
            return (
              <div
                key={signal.id}
                className="rounded border border-borderTone bg-panelSoft p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <SignalBadge signal={signal} />
                    <span className="text-xs text-textMute">
                      {signal.market} • {outcome}
                    </span>
                  </div>
                  <span className="text-xs text-textMute">
                    {new Date(signal.created_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>

                {proAccess && hasActionableSlot && (
                  <div className="mt-2 rounded border border-borderTone/70 bg-panel p-2 text-xs text-textMute">
                    {actionableLoading && !actionable && <p>Loading actionable book card...</p>}
                    {!actionableLoading && !actionable && <p>No actionable book card available.</p>}
                    {actionable && (
                      <div className="space-y-1">
                        <p className="flex flex-wrap items-center gap-2 text-textMain">
                          <span className="rounded border border-borderTone px-1.5 py-0.5 text-[11px]">
                            Rank {actionable.execution_rank}
                          </span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[11px] uppercase tracking-wider ${
                              actionable.freshness_bucket === "fresh"
                                ? "bg-positive/10 text-positive"
                                : actionable.freshness_bucket === "aging"
                                  ? "bg-accent/15 text-accent"
                                  : "bg-negative/15 text-negative"
                            }`}
                          >
                            {actionable.freshness_bucket}
                          </span>
                          <span>
                            Book vs Consensus:{" "}
                            <span className="font-semibold">{actionable.best_book_key ?? "-"}</span>{" "}
                            {actionable.best_line != null
                              ? `${actionable.best_line} (${actionable.best_price ?? "-"})`
                              : actionable.best_price ?? "-"}
                            {" "}vs{" "}
                            {actionable.consensus_line != null
                              ? `${actionable.consensus_line} (${actionable.consensus_price ?? "-"})`
                              : actionable.consensus_price ?? "-"}
                          </span>
                        </p>
                        <p>
                          {actionable.actionable_reason}
                        </p>
                        <p>
                          Delta:{" "}
                          <span className="text-textMain">
                            {actionable.best_delta != null ? actionable.best_delta.toFixed(3) : "-"}
                          </span>{" "}
                          • Books: <span className="text-textMain">{actionable.books_considered}</span>{" "}
                          • Freshness:{" "}
                          <span className={actionable.is_stale ? "text-negative" : "text-positive"}>
                            {actionable.freshness_seconds != null
                              ? `${Math.floor(actionable.freshness_seconds / 60)}m`
                              : "-"}
                          </span>
                        </p>
                        {actionable.top_books.length > 0 && (
                          <p>
                            Top books:{" "}
                            {actionable.top_books.map((book) => (
                              <span key={`${signal.id}-${book.sportsbook_key}`} className="mr-2 inline-block">
                                {book.sportsbook_key}:{" "}
                                {book.line != null ? `${book.line} (${book.price})` : `${book.price}`}
                              </span>
                            ))}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {!proAccess && (
          <p className="mt-3 text-xs text-textMute">
            Free tier hides velocity and actionable book cards. Upgrade to Pro for full signal diagnostics.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-textMute">Context Score Framework</h2>
        <pre className="overflow-auto rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          {JSON.stringify(detail.context_scaffold, null, 2)}
        </pre>
      </div>
    </section>
  );
}
