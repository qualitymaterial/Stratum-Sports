import {
  AdminOutcomesReport,
  AdminApiPartnerEntitlement,
  AdminApiPartnerEntitlementUpdate,
  AdminApiPartnerKeyIssue,
  AdminApiPartnerKeyList,
  AdminApiPartnerKeyRevoke,
  AdminOverview,
  AdminAuditLogList,
  AdminRole,
  AdminBillingMutation,
  AdminBillingOverview,
  AdminUserActiveUpdate,
  AdminUserPasswordReset,
  AdminUserSearchList,
  AdminUserRoleUpdate,
  AdminUserTierUpdate,
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
  OpportunityPoint,
  OpportunityTeaserPoint,
  PublicTeaserKpisResponse,
  PublicTeaserOpportunity,
  SignalLifecycleSummary,
  SignalQualityWeeklySummary,
  SignalQualityRow,
  SportKey,
  User,
  WatchlistItem,
} from "@/lib/types";
import { apiRequest, getApiBaseUrl } from "@/lib/apiClient";

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

export async function requestPasswordReset(email: string) {
  return apiRequest<{ message: string; reset_token?: string; expires_in_minutes?: number }>(
    "/auth/password-reset/request",
    {
      method: "POST",
      body: { email },
    },
  );
}

export async function confirmPasswordReset(token: string, new_password: string) {
  return apiRequest<{ message: string }>("/auth/password-reset/confirm", {
    method: "POST",
    body: { token, new_password },
  });
}

export async function getMe(token: string) {
  return apiRequest<User>("/auth/me", { token });
}

export async function getAdminOverview(
  token: string,
  options: {
    days?: number;
    cycle_limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "cycle_limit", options.cycle_limit);
  return apiRequest<AdminOverview>(`/admin/overview?${params.toString()}`, { token });
}

type AdminOutcomesFilters = {
  days?: number;
  baseline_days?: number;
  sport_key?: SportKey;
  signal_type?: string;
  market?: string;
  time_bucket?: string;
};

function buildAdminOutcomesQuery(options: AdminOutcomesFilters = {}): string {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "baseline_days", options.baseline_days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "time_bucket", options.time_bucket);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function resolveDownloadFilename(
  response: Response,
  fallback: string,
): string {
  const contentDisposition = response.headers.get("Content-Disposition");
  if (!contentDisposition) {
    return fallback;
  }
  const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  if (!match?.[1]) {
    return fallback;
  }
  return match[1];
}

async function downloadFile(
  token: string,
  path: string,
  fallbackFilename: string,
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
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

  const blob = await response.blob();
  if (typeof window === "undefined") {
    return;
  }
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = resolveDownloadFilename(response, fallbackFilename);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export async function getAdminOutcomesReport(
  token: string,
  options: AdminOutcomesFilters = {},
) {
  const query = buildAdminOutcomesQuery(options);
  return apiRequest<AdminOutcomesReport>(`/admin/outcomes/report${query}`, { token });
}

export async function downloadAdminOutcomesJson(
  token: string,
  options: AdminOutcomesFilters = {},
) {
  const query = buildAdminOutcomesQuery(options);
  await downloadFile(token, `/admin/outcomes/export.json${query}`, "admin-outcomes-report.json");
}

export async function downloadAdminOutcomesCsv(
  token: string,
  options: AdminOutcomesFilters & {
    table: "summary" | "by_signal_type" | "by_market" | "top_filtered_reasons";
  },
) {
  const query = buildAdminOutcomesQuery(options);
  const separator = query ? "&" : "?";
  await downloadFile(
    token,
    `/admin/outcomes/export.csv${query}${separator}table=${encodeURIComponent(options.table)}`,
    `admin-outcomes-${options.table}.csv`,
  );
}

export async function updateAdminUserTier(
  token: string,
  userId: string,
  payload: {
    tier: "free" | "pro";
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminUserTierUpdate>(`/admin/users/${userId}/tier`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export async function updateAdminUserRole(
  token: string,
  userId: string,
  payload: {
    admin_role: AdminRole | null;
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminUserRoleUpdate>(`/admin/users/${userId}/role`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export async function updateAdminUserActive(
  token: string,
  userId: string,
  payload: {
    is_active: boolean;
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminUserActiveUpdate>(`/admin/users/${userId}/active`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export async function requestAdminUserPasswordReset(
  token: string,
  userId: string,
  payload: {
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminUserPasswordReset>(`/admin/users/${userId}/password-reset`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function getAdminUserBilling(
  token: string,
  userId: string,
) {
  return apiRequest<AdminBillingOverview>(`/admin/users/${userId}/billing`, { token });
}

export async function resyncAdminUserBilling(
  token: string,
  userId: string,
  payload: {
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminBillingMutation>(`/admin/users/${userId}/billing/resync`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function cancelAdminUserBilling(
  token: string,
  userId: string,
  payload: {
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminBillingMutation>(`/admin/users/${userId}/billing/cancel`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function reactivateAdminUserBilling(
  token: string,
  userId: string,
  payload: {
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminBillingMutation>(`/admin/users/${userId}/billing/reactivate`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function getAdminUserApiPartnerKeys(
  token: string,
  userId: string,
) {
  return apiRequest<AdminApiPartnerKeyList>(`/admin/users/${userId}/api-keys`, { token });
}

export async function issueAdminUserApiPartnerKey(
  token: string,
  userId: string,
  payload: {
    name: string;
    expires_in_days?: number;
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminApiPartnerKeyIssue>(`/admin/users/${userId}/api-keys`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function revokeAdminUserApiPartnerKey(
  token: string,
  userId: string,
  keyId: string,
  payload: {
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminApiPartnerKeyRevoke>(`/admin/users/${userId}/api-keys/${keyId}/revoke`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function rotateAdminUserApiPartnerKey(
  token: string,
  userId: string,
  keyId: string,
  payload: {
    name?: string;
    expires_in_days?: number;
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminApiPartnerKeyIssue>(`/admin/users/${userId}/api-keys/${keyId}/rotate`, {
    method: "POST",
    token,
    body: payload,
  });
}

export async function getAdminUserApiPartnerEntitlement(
  token: string,
  userId: string,
) {
  return apiRequest<AdminApiPartnerEntitlement>(`/admin/users/${userId}/api-entitlement`, { token });
}

export async function updateAdminUserApiPartnerEntitlement(
  token: string,
  userId: string,
  payload: {
    plan_code?: "api_monthly" | "api_annual" | null;
    api_access_enabled?: boolean;
    soft_limit_monthly?: number | null;
    overage_enabled?: boolean;
    overage_price_cents?: number | null;
    overage_unit_quantity?: number;
    reason: string;
    step_up_password: string;
    confirm_phrase: string;
  },
) {
  return apiRequest<AdminApiPartnerEntitlementUpdate>(`/admin/users/${userId}/api-entitlement`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export async function getAdminAuditLogs(
  token: string,
  options: {
    limit?: number;
    offset?: number;
    action_type?: string;
    target_type?: string;
    actor_user_id?: string;
    target_id?: string;
    since?: string;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "limit", options.limit);
  appendOptionalParam(params, "offset", options.offset);
  appendOptionalParam(params, "action_type", options.action_type);
  appendOptionalParam(params, "target_type", options.target_type);
  appendOptionalParam(params, "actor_user_id", options.actor_user_id);
  appendOptionalParam(params, "target_id", options.target_id);
  appendOptionalParam(params, "since", options.since);
  const query = params.toString();
  return apiRequest<AdminAuditLogList>(`/admin/audit/logs${query ? `?${query}` : ""}`, { token });
}

export async function getAdminUsers(
  token: string,
  options: {
    q: string;
    limit?: number;
  },
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "q", options.q);
  appendOptionalParam(params, "limit", options.limit);
  return apiRequest<AdminUserSearchList>(`/admin/users?${params.toString()}`, { token });
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

export async function getDashboardCards(
  token: string,
  options: {
    sport_key?: SportKey;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "sport_key", options.sport_key);
  const query = params.toString();
  return apiRequest<DashboardCard[]>(`/dashboard/cards${query ? `?${query}` : ""}`, { token });
}

export async function getGameDetail(eventId: string, token: string) {
  return apiRequest<GameDetail>(`/games/${eventId}`, { token });
}

export async function getGames(
  token: string,
  options: {
    sport_key?: SportKey;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "sport_key", options.sport_key);
  const query = params.toString();
  return apiRequest<GameListItem[]>(`/games${query ? `?${query}` : ""}`, { token });
}

export async function getWatchlist(
  token: string,
  options: {
    sport_key?: SportKey;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "sport_key", options.sport_key);
  const query = params.toString();
  return apiRequest<WatchlistItem[]>(`/watchlist${query ? `?${query}` : ""}`, { token });
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
    thresholds: {
      min_books_affected: number;
      max_dispersion: number | null;
      cooldown_minutes: number;
    };
  },
) {
  return apiRequest<DiscordConnection>("/discord/connection", {
    method: "PUT",
    token,
    body: payload,
  });
}

function appendOptionalParam(
  params: URLSearchParams,
  key: string,
  value: string | number | boolean | null | undefined,
) {
  if (value === undefined || value === null || value === "") {
    return;
  }
  params.set(key, String(value));
}

export async function getClvSummary(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
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
    sport_key?: SportKey;
    grain?: "day" | "week";
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
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
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_samples?: number;
    min_strength?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_samples", options.min_samples);
  appendOptionalParam(params, "min_strength", options.min_strength);

  return apiRequest<ClvTrustScorecard[]>(`/intel/clv/scorecards?${params.toString()}`, { token });
}

type ClvRecordFilters = {
  days?: number;
  sport_key?: SportKey;
  event_id?: string;
  signal_type?: string;
  market?: string;
  min_strength?: number;
  limit?: number;
  offset?: number;
};

function buildClvRecordsQuery(options: ClvRecordFilters = {}): string {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "event_id", options.event_id);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "limit", options.limit);
  appendOptionalParam(params, "offset", options.offset);
  return params.toString();
}

export async function getClvRecords(
  token: string,
  options: ClvRecordFilters = {},
) {
  const query = buildClvRecordsQuery(options);
  const suffix = query ? `?${query}` : "";
  return apiRequest<ClvRecordPoint[]>(`/intel/clv${suffix}`, { token });
}

export async function downloadClvRecordsCsv(
  token: string,
  options: ClvRecordFilters = {},
) {
  const query = buildClvRecordsQuery(options);
  const suffix = query ? `?${query}` : "";
  await downloadFile(token, `/intel/clv/export.csv${suffix}`, "clv-records.csv");
}

export async function getSignalQuality(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    min_books_affected?: number;
    max_dispersion?: number;
    window_minutes_max?: number;
    apply_alert_rules?: boolean;
    include_hidden?: boolean;
    limit?: number;
    offset?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "min_books_affected", options.min_books_affected);
  appendOptionalParam(params, "max_dispersion", options.max_dispersion);
  appendOptionalParam(params, "window_minutes_max", options.window_minutes_max);
  appendOptionalParam(params, "apply_alert_rules", options.apply_alert_rules);
  appendOptionalParam(params, "include_hidden", options.include_hidden);
  appendOptionalParam(params, "limit", options.limit);
  appendOptionalParam(params, "offset", options.offset);

  return apiRequest<SignalQualityRow[]>(`/intel/signals/quality?${params.toString()}`, { token });
}

export async function getSignalQualityWeeklySummary(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    apply_alert_rules?: boolean;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "apply_alert_rules", options.apply_alert_rules);

  return apiRequest<SignalQualityWeeklySummary>(`/intel/signals/weekly-summary?${params.toString()}`, { token });
}

export async function getSignalLifecycleSummary(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    apply_alert_rules?: boolean;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "apply_alert_rules", options.apply_alert_rules);
  return apiRequest<SignalLifecycleSummary>(`/intel/signals/lifecycle?${params.toString()}`, { token });
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

export async function getClvTeaser(token: string, days = 30, sport_key?: SportKey) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", days);
  appendOptionalParam(params, "sport_key", sport_key);
  return apiRequest<ClvTeaserResponse>(`/intel/clv/teaser?${params.toString()}`, { token });
}

export async function getBestOpportunities(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    min_edge?: number;
    max_width?: number;
    include_stale?: boolean;
    limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "min_edge", options.min_edge);
  appendOptionalParam(params, "max_width", options.max_width);
  appendOptionalParam(params, "include_stale", options.include_stale);
  appendOptionalParam(params, "limit", options.limit);

  return apiRequest<OpportunityPoint[]>(`/intel/opportunities?${params.toString()}`, { token });
}

export async function getOpportunityTeaser(
  token: string,
  options: {
    days?: number;
    sport_key?: SportKey;
    signal_type?: string;
    market?: string;
    min_strength?: number;
    limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "days", options.days);
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "signal_type", options.signal_type);
  appendOptionalParam(params, "market", options.market);
  appendOptionalParam(params, "min_strength", options.min_strength);
  appendOptionalParam(params, "limit", options.limit);

  return apiRequest<OpportunityTeaserPoint[]>(`/intel/opportunities/teaser?${params.toString()}`, { token });
}

export async function trackTeaserInteraction(
  token: string,
  payload: {
    event_name: "viewed_teaser" | "clicked_upgrade_from_teaser";
    source?: string;
    sport_key?: SportKey;
  },
) {
  return apiRequest<{ status: string }>("/intel/teaser/events", {
    method: "POST",
    token,
    body: payload,
  });
}

export async function getPublicTeaserOpportunities(options: {
  sport_key?: SportKey;
  limit?: number;
} = {}) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "limit", options.limit);
  const query = params.toString();
  return apiRequest<PublicTeaserOpportunity[]>(`/public/teaser/opportunities${query ? `?${query}` : ""}`);
}

export async function getPublicTeaserKpis(options: {
  sport_key?: SportKey;
  window_hours?: number;
} = {}) {
  const params = new URLSearchParams();
  appendOptionalParam(params, "sport_key", options.sport_key);
  appendOptionalParam(params, "window_hours", options.window_hours);
  const query = params.toString();
  return apiRequest<PublicTeaserKpisResponse>(`/public/teaser/kpis${query ? `?${query}` : ""}`);
}
