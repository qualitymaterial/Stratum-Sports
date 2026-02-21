import {
  DashboardCard,
  DiscordConnection,
  GameDetail,
  GameListItem,
  User,
  WatchlistItem,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

async function apiRequest<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    token?: string;
    body?: unknown;
    headers?: Record<string, string>;
  } = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.headers ?? {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = payload.detail;
      }
    } catch {
      // ignore parse failures
    }
    throw new Error(message);
  }

  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text) as T;
}

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
  return apiRequest<{ url: string }>("/auth/discord/login");
}

export async function discordCallback(code: string) {
  return apiRequest<{ access_token: string; user: User }>(
    `/auth/discord/callback?code=${code}`,
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
