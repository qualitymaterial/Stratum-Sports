"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { MovementChart } from "@/components/MovementChart";
import { SignalBadge } from "@/components/SignalBadge";
import { getGameDetail } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/apiClient";
import { useCurrentUser } from "@/lib/auth";
import { GameDetail } from "@/lib/types";

const API_BASE = getApiBaseUrl();

export default function GameDetailPage() {
  const params = useParams<{ event_id: string }>();
  const eventId = params.event_id;
  const { user, loading, token } = useCurrentUser(true);

  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

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
          {user.tier === "pro" ? (
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
        <div className="flex flex-wrap gap-2">
          {detail.signals.map((signal) => (
            <SignalBadge key={signal.id} signal={signal} />
          ))}
          {detail.signals.length === 0 && (
            <p className="text-sm text-textMute">No signals recorded yet.</p>
          )}
        </div>

        {user.tier === "free" && (
          <p className="mt-3 text-xs text-textMute">
            Free tier hides velocity and book-level metadata. Upgrade to Pro for full signal diagnostics.
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
