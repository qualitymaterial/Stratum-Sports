"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { addWatchlist, getGames, getWatchlist, removeWatchlist } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { GameListItem, WatchlistItem } from "@/lib/types";

export default function WatchlistPage() {
  const { user, loading, token } = useCurrentUser(true);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [games, setGames] = useState<GameListItem[]>([]);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!token) {
      return;
    }
    setError(null);
    try {
      const [watch, allGames] = await Promise.all([getWatchlist(token), getGames(token)]);
      setWatchlist(watch);
      setGames(allGames);
      if (!selectedEventId && allGames.length > 0) {
        setSelectedEventId(allGames[0].event_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load watchlist");
    }
  };

  useEffect(() => {
    if (!loading && token) {
      void load();
    }
  }, [loading, token]);

  const options = useMemo(
    () => games.filter((game) => !watchlist.some((item) => item.event_id === game.event_id)),
    [games, watchlist],
  );

  const onAdd = async () => {
    if (!token || !selectedEventId) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addWatchlist(selectedEventId, token);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add game");
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async (eventId: string) => {
    if (!token) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await removeWatchlist(eventId, token);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove game");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !user) {
    return <LoadingState label="Loading watchlist..." />;
  }
  const proAccess = hasProAccess(user);

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Watchlist</h1>
        <p className="text-sm text-textMute">
          {proAccess
            ? "Unlimited tracking and Discord alerts enabled."
            : "Free tier max watchlist size: 3 games. Discord alerts are Pro only."}
        </p>
      </header>

      {error && <p className="text-sm text-negative">{error}</p>}

      <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
        <p className="mb-3 text-xs uppercase tracking-wider text-textMute">Add Game</p>
        <div className="flex flex-col gap-2 md:flex-row">
          <select
            value={selectedEventId}
            onChange={(event) => setSelectedEventId(event.target.value)}
            className="w-full rounded border border-borderTone bg-panelSoft px-3 py-2 text-sm md:w-[420px]"
          >
            {options.length === 0 && <option value="">No games available</option>}
            {options.map((game) => (
              <option key={game.event_id} value={game.event_id}>
                {game.away_team} @ {game.home_team}
              </option>
            ))}
          </select>
          <button
            disabled={busy || !selectedEventId || options.length === 0}
            onClick={() => {
              void onAdd();
            }}
            className="rounded border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50"
          >
            Add to Watchlist
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
        <p className="mb-3 text-xs uppercase tracking-wider text-textMute">Tracked Games</p>
        <div className="space-y-2">
          {watchlist.length === 0 && <p className="text-sm text-textMute">No games on your watchlist.</p>}

          {watchlist.map((item) => (
            <div
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-borderTone bg-panelSoft p-3"
            >
              <div>
                <p className="text-sm text-textMain">
                  {item.game ? `${item.game.away_team} @ ${item.game.home_team}` : item.event_id}
                </p>
                {item.game && (
                  <p className="text-xs text-textMute">
                    {new Date(item.game.commence_time).toLocaleString([], {
                      month: "short",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                )}
              </div>

              <div className="flex gap-2">
                <Link
                  href={`/app/games/${item.event_id}`}
                  className="rounded border border-borderTone px-2 py-1 text-xs text-textMute hover:border-accent hover:text-accent"
                >
                  Open
                </Link>
                <button
                  disabled={busy}
                  onClick={() => {
                    void onRemove(item.event_id);
                  }}
                  className="rounded border border-borderTone px-2 py-1 text-xs text-textMute hover:border-negative hover:text-negative"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {!proAccess && (
        <div className="rounded-xl border border-borderTone bg-panel p-4 text-sm text-textMute shadow-terminal">
          Discord webhooks, real-time stream, and detailed signal diagnostics are locked to Pro.
        </div>
      )}
    </section>
  );
}
