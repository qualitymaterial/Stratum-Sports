"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { addWatchlist, getGames, getWatchlist, removeWatchlist } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { GameListItem, SportKey, WatchlistItem } from "@/lib/types";

const WATCHLIST_SPORT_STORAGE_KEY = "stratum_watchlist_sport";
const WATCHLIST_SPORT_OPTIONS: Array<{ key: SportKey; label: string }> = [
  { key: "basketball_nba", label: "NBA" },
  { key: "basketball_ncaab", label: "NCAA M" },
  { key: "americanfootball_nfl", label: "NFL" },
];

function resolveSport(raw: string | null | undefined): SportKey | null {
  if (raw === "basketball_nba" || raw === "basketball_ncaab" || raw === "americanfootball_nfl") {
    return raw;
  }
  return null;
}

export default function WatchlistPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, loading, token } = useCurrentUser(true);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [games, setGames] = useState<GameListItem[]>([]);
  const [selectedSport, setSelectedSport] = useState<SportKey>("basketball_nba");
  const [sportHydrated, setSportHydrated] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const fromUrl = resolveSport(searchParams.get("sport_key"));
    if (fromUrl) {
      setSelectedSport(fromUrl);
      setSportHydrated(true);
      return;
    }

    if (typeof window !== "undefined") {
      const fromStorage = resolveSport(window.localStorage.getItem(WATCHLIST_SPORT_STORAGE_KEY));
      if (fromStorage) {
        setSelectedSport(fromStorage);
      }
    }
    setSportHydrated(true);
  }, [searchParams]);

  useEffect(() => {
    if (!sportHydrated || typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(WATCHLIST_SPORT_STORAGE_KEY, selectedSport);
    const params = new URLSearchParams(searchParams.toString());
    if (params.get("sport_key") !== selectedSport) {
      params.set("sport_key", selectedSport);
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    }
  }, [selectedSport, sportHydrated, searchParams, router, pathname]);

  const load = async () => {
    if (!token) {
      return;
    }
    setError(null);
    try {
      const [watch, allGames] = await Promise.all([
        getWatchlist(token, { sport_key: selectedSport }),
        getGames(token, { sport_key: selectedSport }),
      ]);
      setWatchlist(watch);
      setGames(allGames);
      setSelectedEventId((current) => {
        if (allGames.length === 0) {
          return "";
        }
        const stillPresent = allGames.some((game) => game.event_id === current);
        return stillPresent ? current : allGames[0].event_id;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load watchlist");
    }
  };

  useEffect(() => {
    if (!sportHydrated) {
      return;
    }
    if (!loading && token) {
      void load();
    }
  }, [loading, token, selectedSport, sportHydrated]);

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
        <div className="mt-3 inline-flex flex-wrap gap-2">
          {WATCHLIST_SPORT_OPTIONS.map((option) => {
            const active = option.key === selectedSport;
            return (
              <button
                key={option.key}
                onClick={() => setSelectedSport(option.key)}
                className={`rounded border px-2.5 py-1 text-xs uppercase tracking-wider transition ${
                  active
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-borderTone text-textMute hover:border-accent hover:text-accent"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
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
