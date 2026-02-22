import {
  ActionableBookCard,
  ClvRecapResponse,
  ClvPerformanceRow,
  ClvRecordPoint,
  ClvTrustScorecard,
  ClvTeaserResponse,
  DashboardCard,
  DiscordConnection,
  GameDetail,
  GameListItem,
  SignalQualityRow,
  User,
  WatchlistItem,
} from "@/lib/types";
import { apiRequest } from "@/lib/apiClient";

export async function register(email: string, password: string) {
  return apiRequest<{ access_token: string; user: User }>("/auth/register", {
    method: "POST",
    body: { email, password },
  });
}

export async function login(email: string, password: string) {
  return apiRequest<{ access_token: string; user: User }>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export async function getMe(token: string) {
  return apiRequest<User>("/auth/me", { token });
}

export async function getDiscordAuthUrl() {
  return apiRequest<{ url: string; state: string }>("/auth/discord/login");
}

export async function discordCallback(code: string, state: string) {
  const params = new URLSearchParams({ code, state });
  return apiRequest<{ access_token: string; user: User }>(
    `/auth/discord/callback?${params.toString()}`,
    { method: "POST" },
  );
}

export async function getDashboardCards(token: string) {
  return apiRequest<DashboardCard[]>("/dashboard/cards", { token });
}

export async function getGameDetail(eventId: string, token: string) {
  return apiRequest<GameDetail>(`/games/${eventId}`, { token });
}

export async function getGames(token: string) {
  return apiRequest<GameListItem[]>("/games", { token });
}

export async function getWatchlist(token: string) {
  return apiRequest<WatchlistItem[]>("/watchlist", { token });
}

export async function addWatchlist(eventId: string, token: string) {
  return apiRequest<{ status: string }>(`/watchlist/${eventId}`, {
    method: "POST",
    token,
  });
}

export async function removeWatchlist(eventId: string, token: string) {
  return apiRequest<{ status: string }>(`/watchlist/${eventId}`, {
    method: "DELETE",
    token,
  });
}

export async function createCheckoutSession(token: string) {
  return apiRequest<{ url: string }>("/billing/create-checkout-session", {
    method: "POST",
    token,
  });
}

export async function createPortalSession(token: string) {
  return apiRequest<{ url: string }>("/billing/portal", {
    method: "POST",
    token,
  });
}

export async function getDiscordConnection(token: string) {
  return apiRequest<DiscordConnection>("/discord/connection", { token });
}

export async function upsertDiscordConnection(
  token: string,
  payload: {
    webhook_url: string;
    is_enabled: boolean;
    alert_spreads: boolean;
    alert_totals: boolean;
    alert_multibook: boolean;
    min_strength: number;
  },
) {
  return apiRequest<DiscordConnection>("/discord/connection", {
    method: "PUT",
    token,
    body: payload,
  });
}

function appendOptionalParam(params: URLSearchParams, key: string, value: string | number | null | undefined) {
  if (value === undefined || value === null || value === "") {
    return;
  }
  params.set(key, String(value));
}

export async function getClvSummary(
  token: string,
  options: {
    days?: number;
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_samples", options.min_samples);
  appendOptionalParam(params, "min_strength", options.min_strength);

  return apiRequest<ClvPerformanceRow[]>(`/intel/clv/summary?${params.toString()}`, { token });
}

export async function getClvRecap(
  token: string,
  options: {
    days?: number;
    grain?: "day" | "week";
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "grain", options.grain);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_samples", options.min_samples);
  appendOptionalParam(params, "min_strength", options.min_strength);

  return apiRequest<ClvRecapResponse>(`/intel/clv/recap?${params.toString()}`, { token });
}

export async function getClvTrustScorecards(
  token: string,
  options: {
    days?: number;
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_samples", options.min_samples);
  appendOptionalParam(params, "min_strength", options.min_strength);

  return apiRequest<ClvTrustScorecard[]>(`/intel/clv/scorecards?${params.toString()}`, { token });
}

export async function getClvRecords(
  token: string,
  options: {
    days?: number;
    event_id?: string;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    limit?: number;
    offset?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "event_id", options.event_id);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "limit", options.limit);
  appendOptionalParam(params, "offset", options.offset);

  return apiRequest<ClvRecordPoint[]>(`/intel/clv?${params.toString()}`, { token });
}

export async function getSignalQuality(
  token: string,
  options: {
    days?: number;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    min_books_affected?: number;
    max_dispersion?: number;
    window_minutes_max?: number;
    limit?: number;
    offset?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "min_books_affected", options.min_books_affected);
  appendOptionalParam(params, "max_dispersion", options.max_dispersion);
  appendOptionalParam(params, "window_minutes_max", options.window_minutes_max);
  appendOptionalParam(params, "limit", options.limit);
  appendOptionalParam(params, "offset", options.offset);

  return apiRequest<SignalQualityRow[]>(`/intel/signals/quality?${params.toString()}`, { token });
}

export async function getActionableBookCard(token: string, eventId: string, signalId: string) {
  const params = new URLSearchParams({
    event_id: eventId,
    signal_id: signalId,
  });
  return apiRequest<ActionableBookCard>(`/intel/books/actionable?${params.toString()}`, { token });
}

export async function getActionableBookCardsBatch(
  token: string,
  eventId: string,
  signalIds: string[],
) {
  if (signalIds.length === 0) {
    return [] as ActionableBookCard[];
  }
  const params = new URLSearchParams({
    event_id: eventId,
    signal_ids: signalIds.join(","),
  });
  return apiRequest<ActionableBookCard[]>(`/intel/books/actionable/batch?${params.toString()}`, { token });
}

export async function getClvTeaser(token: string, days = 30) {
  return apiRequest<ClvTeaserResponse>(`/intel/clv/teaser?days=${days}`, { token });
}
