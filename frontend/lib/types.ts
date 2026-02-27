export type User = {
  id: string;
  email: string;
  tier: "free" | "pro";
  is_admin: boolean;
  admin_role: "super_admin" | "ops_admin" | "support_admin" | "billing_admin" | null;
  mfa_enabled: boolean;
  created_at: string;
};

export type SportKey = "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl";

export type Signal = {
  id: string;
  event_id: string;
  market: string;
  signal_type: "MOVE" | "KEY_CROSS" | "MULTIBOOK_SYNC" | "DISLOCATION" | "STEAM" | "EXCHANGE_DIVERGENCE";
  display_type?: string | null;
  direction: "UP" | "DOWN";
  from_value: number;
  to_value: number;
  from_price: number | null;
  to_price: number | null;
  window_minutes: number;
  books_affected: number;
  velocity_minutes: number | null;
  freshness_seconds: number;
  freshness_bucket: "fresh" | "aging" | "stale";
  strength_score: number;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type DashboardCard = {
  event_id: string;
  sport_key: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  consensus: {
    spreads: number | null;
    totals: number | null;
    h2h_home: number | null;
    h2h_away: number | null;
  };
  sparkline: number[];
  signals: Signal[];
};

export type GameDetail = {
  event_id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  odds: Array<{
    sportsbook_key: string;
    market: string;
    outcome_name: string;
    line: number | null;
    price: number;
    fetched_at: string;
  }>;
  chart_series: Array<{
    timestamp: string;
    spreads: number | null;
    totals: number | null;
    h2h_home: number | null;
    h2h_away: number | null;
  }>;
  signals: Signal[];
  context_scaffold: {
    event_id: string;
    components: Array<Record<string, unknown>>;
  };
};

export type WatchlistItem = {
  id: string;
  event_id: string;
  created_at: string;
  game: {
    sport_key: SportKey;
    home_team: string;
    away_team: string;
    commence_time: string;
  } | null;
};

export type GameListItem = {
  event_id: string;
  sport_key: string;
  commence_time: string;
  home_team: string;
  away_team: string;
};

export type DiscordConnection = {
  id: string;
  webhook_url: string;
  is_enabled: boolean;
  alert_spreads: boolean;
  alert_totals: boolean;
  alert_multibook: boolean;
  min_strength: number;
  thresholds: {
    min_books_affected?: number;
    max_dispersion?: number | null;
    cooldown_minutes?: number;
  };
  created_at: string;
  updated_at: string;
};

export type ClvPerformanceRow = {
  signal_type: string;
  market: string;
  count: number;
  pct_positive_clv: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
};

export type ClvRecapRow = {
  period_start: string;
  signal_type: string;
  market: string;
  count: number;
  pct_positive_clv: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
};

export type ClvRecapResponse = {
  days: number;
  grain: "day" | "week";
  rows: ClvRecapRow[];
};

export type ClvRecordPoint = {
  signal_id: string;
  event_id: string;
  signal_type: string;
  market: string;
  outcome_name: string;
  strength_score: number;
  entry_line: number | null;
  entry_price: number | null;
  close_line: number | null;
  close_price: number | null;
  clv_line: number | null;
  clv_prob: number | null;
  computed_at: string;
};

export type ClvTeaserResponse = {
  days: number;
  total_records: number;
  rows: ClvPerformanceRow[];
};

export type ClvTrustScorecard = {
  signal_type: string;
  market: string;
  count: number;
  pct_positive_clv: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
  stddev_clv_line: number | null;
  stddev_clv_prob: number | null;
  confidence_score: number;
  confidence_tier: "A" | "B" | "C";
  stability_ratio_line: number | null;
  stability_ratio_prob: number | null;
  stability_label: "stable" | "moderate" | "noisy" | "unknown";
  score_components: {
    sample_points: number;
    edge_points: number;
    stability_points: number;
  };
};

export type SignalQualityRow = {
  id: string;
  event_id: string;
  game_label: string | null;
  game_commence_time: string | null;
  market: string;
  signal_type: string;
  display_type?: string | null;
  direction: string;
  strength_score: number;
  books_affected: number;
  window_minutes: number;
  created_at: string;
  outcome_name: string | null;
  book_key: string | null;
  delta: number | null;
  dispersion: number | null;
  freshness_seconds: number;
  freshness_bucket: "fresh" | "aging" | "stale" | string;
  lifecycle_stage: "sent" | "filtered" | "stale" | "eligible" | string;
  lifecycle_reason: string;
  alert_decision: "sent" | "hidden" | string;
  alert_reason: string;
  metadata: Record<string, unknown>;
};

export type SignalLifecycleReasonCount = {
  reason: string;
  count: number;
};

export type SignalLifecycleSummary = {
  days: number;
  total_detected: number;
  eligible_signals: number;
  sent_signals: number;
  filtered_signals: number;
  stale_signals: number;
  not_sent_signals: number;
  top_filtered_reasons: SignalLifecycleReasonCount[];
};

export type SignalQualityWeeklySummary = {
  days: number;
  total_signals: number;
  eligible_signals: number;
  hidden_signals: number;
  sent_rate_pct: number;
  avg_strength: number | null;
  clv_samples: number;
  clv_pct_positive: number;
  top_hidden_reason: string | null;
};

export type ActionableBookQuote = {
  sportsbook_key: string;
  line: number | null;
  price: number;
  fetched_at: string;
  delta: number | null;
};

export type ActionableBookCard = {
  event_id: string;
  signal_id: string;
  signal_type: string;
  display_type?: string | null;
  market: string;
  outcome_name: string | null;
  direction: string;
  strength_score: number;
  consensus_line: number | null;
  consensus_price: number | null;
  dispersion: number | null;
  consensus_source: string;
  best_book_key: string | null;
  best_line: number | null;
  best_price: number | null;
  best_delta: number | null;
  delta_type: string;
  fetched_at: string | null;
  freshness_seconds: number | null;
  freshness_bucket: "fresh" | "aging" | "stale";
  is_stale: boolean;
  execution_rank: number;
  actionable_reason: string;
  books_considered: number;
  top_books: ActionableBookQuote[];
  quotes: ActionableBookQuote[];
};

export type OpportunityPoint = {
  signal_id: string;
  event_id: string;
  game_label: string | null;
  game_commence_time: string | null;
  signal_type: string;
  display_type?: string | null;
  market: string;
  outcome_name: string | null;
  direction: string;
  strength_score: number;
  created_at: string;
  best_book_key: string | null;
  best_line: number | null;
  best_price: number | null;
  consensus_line: number | null;
  consensus_price: number | null;
  best_delta: number | null;
  best_edge_line: number | null;
  best_edge_prob: number | null;
  market_width: number | null;
  delta_type: string;
  books_considered: number;
  freshness_seconds: number | null;
  freshness_bucket: "fresh" | "aging" | "stale" | string;
  execution_rank: number;
  clv_prior_samples: number | null;
  clv_prior_pct_positive: number | null;
  opportunity_score: number;
  context_score?: number | null;
  blended_score?: number | null;
  ranking_score?: number;
  score_basis?: "opportunity" | "blended";
  score_components: {
    strength: number;
    execution: number;
    delta: number;
    books: number;
    freshness: number;
    clv_prior: number;
    dispersion_penalty: number;
    stale_cap_penalty: number;
  };
  score_summary: string;
  opportunity_status: "actionable" | "monitor" | "stale" | string;
  reason_tags: string[];
  actionable_reason: string;
};

export type OpportunityTeaserPoint = {
  event_id: string;
  game_label: string | null;
  game_commence_time: string | null;
  signal_type: string;
  display_type?: string | null;
  market: string;
  outcome_name: string | null;
  direction: string;
  strength_score: number;
  created_at: string;
  freshness_bucket: "fresh" | "aging" | "stale" | string;
  books_considered: number;
  opportunity_status: "actionable" | "monitor" | "stale" | string;
};

export type PublicTeaserOpportunity = {
  game_label: string | null;
  commence_time: string | null;
  signal_type: string;
  display_type?: string | null;
  market: string;
  outcome_name: string | null;
  score_status: "ACTIONABLE" | "MONITOR" | "STALE";
  freshness_label: "Fresh" | "Aging" | "Stale";
  delta_display: string;
};

export type PublicTeaserKpisResponse = {
  signals_in_window: number;
  books_tracked_estimate: number;
  pct_actionable: number;
  pct_fresh: number;
  updated_at: string;
};

export type AdminClvBySignalType = {
  signal_type: string;
  count: number;
  pct_positive: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
};

export type AdminClvByMarket = {
  market: string;
  count: number;
  pct_positive: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
};

export type AdminOperatorReport = {
  days: number;
  period_start: string;
  period_end: string;
  ops: {
    total_cycles: number;
    avg_cycle_duration_ms: number | null;
    degraded_cycles: number;
    total_requests_used: number;
    avg_requests_remaining: number | null;
    total_snapshots_inserted: number;
    total_consensus_points_written: number;
    total_signals_created: number;
    signals_created_by_type: Record<string, number>;
  };
  performance: {
    clv_by_signal_type: AdminClvBySignalType[];
    clv_by_market: AdminClvByMarket[];
  };
  reliability: {
    alerts_sent: number;
    alerts_failed: number;
    alert_failure_rate: number;
  };
};

export type AdminCycleKpi = {
  id: string;
  cycle_id: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  requests_used_delta: number | null;
  requests_remaining: number | null;
  requests_limit: number | null;
  events_processed: number | null;
  snapshots_inserted: number | null;
  consensus_points_written: number | null;
  signals_created_total: number | null;
  signals_created_by_type: Record<string, number> | null;
  alerts_sent: number | null;
  alerts_failed: number | null;
  error: string | null;
  degraded: boolean;
  notes: Record<string, unknown> | null;
  created_at: string;
};

export type AdminOverview = {
  report: AdminOperatorReport;
  recent_cycles: AdminCycleKpi[];
  conversion: {
    days: number;
    period_start: string;
    period_end: string;
    teaser_views: number;
    teaser_clicks: number;
    click_through_rate: number;
    unique_viewers: number;
    unique_clickers: number;
    by_sport: Array<{
      sport_key: string;
      teaser_views: number;
      teaser_clicks: number;
      click_through_rate: number;
    }>;
  };
};

export type AdminOutcomesKpiSet = {
  clv_samples: number;
  positive_count: number;
  negative_count: number;
  clv_positive_rate: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
  sent_rate: number;
  stale_rate: number;
  degraded_cycle_rate: number;
  alert_failure_rate: number;
};

export type AdminOutcomesDelta = {
  clv_samples_delta: number;
  positive_count_delta: number;
  negative_count_delta: number;
  clv_positive_rate_delta: number;
  avg_clv_line_delta: number | null;
  avg_clv_prob_delta: number | null;
  sent_rate_delta: number;
  stale_rate_delta: number;
  degraded_cycle_rate_delta: number;
  alert_failure_rate_delta: number;
};

export type AdminOutcomesBreakdownRow = {
  name: string;
  count: number;
  positive_rate: number;
  avg_clv_line: number | null;
  avg_clv_prob: number | null;
};

export type AdminOutcomesFilteredReasonRow = {
  reason: string;
  count: number;
};

export type AdminOutcomesReport = {
  period_start: string;
  period_end: string;
  baseline_period_start: string;
  baseline_period_end: string;
  kpis: AdminOutcomesKpiSet;
  baseline_kpis: AdminOutcomesKpiSet;
  delta_vs_baseline: AdminOutcomesDelta;
  status: string;
  status_reason: string;
  by_signal_type: AdminOutcomesBreakdownRow[];
  by_market: AdminOutcomesBreakdownRow[];
  top_filtered_reasons: AdminOutcomesFilteredReasonRow[];
};

export type AdminRole = "super_admin" | "ops_admin" | "support_admin" | "billing_admin";

export type AdminUserSearchItem = {
  id: string;
  email: string;
  tier: "free" | "pro" | string;
  is_active: boolean;
  is_admin: boolean;
  admin_role: AdminRole | null;
  created_at: string;
};

export type AdminUserSearchList = {
  total: number;
  limit: number;
  items: AdminUserSearchItem[];
};

export type AdminUserTierUpdate = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  old_tier: "free" | "pro" | string;
  new_tier: "free" | "pro" | string;
  reason: string;
};

export type AdminUserRoleUpdate = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  old_admin_role: AdminRole | null;
  new_admin_role: AdminRole | null;
  old_is_admin: boolean;
  new_is_admin: boolean;
  reason: string;
};

export type AdminUserActiveUpdate = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  old_is_active: boolean;
  new_is_active: boolean;
  reason: string;
};

export type AdminUserPasswordReset = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  reason: string;
  message: string;
  reset_token: string | null;
  expires_in_minutes: number | null;
};

export type AdminBillingOverview = {
  user_id: string;
  email: string;
  tier: string;
  is_active: boolean;
  stripe_customer_id: string | null;
  subscription: {
    id: string;
    stripe_subscription_id: string;
    stripe_price_id: string;
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    created_at: string;
    updated_at: string;
  } | null;
};

export type AdminBillingMutation = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  reason: string;
  operation: "resync" | "cancel" | "reactivate";
  previous_status: string | null;
  new_status: string | null;
  previous_cancel_at_period_end: boolean | null;
  new_cancel_at_period_end: boolean | null;
  subscription_id: string | null;
};

export type AdminApiPartnerKey = {
  id: string;
  user_id: string;
  created_by_user_id: string | null;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminApiPartnerKeyList = {
  user_id: string;
  email: string;
  tier: string;
  total_keys: number;
  active_keys: number;
  recently_used_30d: number;
  items: AdminApiPartnerKey[];
};

export type AdminApiPartnerKeyIssue = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  reason: string;
  operation: "issue" | "rotate";
  key: AdminApiPartnerKey;
  api_key: string;
};

export type AdminApiPartnerKeyRevoke = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  reason: string;
  operation: "revoke";
  key_id: string;
  key_prefix: string;
  old_is_active: boolean;
  new_is_active: boolean;
  revoked_at: string | null;
};

export type AdminApiPartnerEntitlement = {
  entitlement_id: string | null;
  user_id: string;
  email: string;
  plan_code: "api_monthly" | "api_annual" | null;
  api_access_enabled: boolean;
  soft_limit_monthly: number | null;
  overage_enabled: boolean;
  overage_price_cents: number | null;
  overage_unit_quantity: number;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminApiPartnerEntitlementUpdate = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  user_id: string;
  email: string;
  reason: string;
  old_entitlement: AdminApiPartnerEntitlement;
  new_entitlement: AdminApiPartnerEntitlement;
};

export type AdminAuditLogItem = {
  id: string;
  actor_user_id: string;
  action_type: string;
  target_type: string;
  target_id: string | null;
  reason: string;
  before_payload: Record<string, unknown> | null;
  after_payload: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string;
};

export type AdminAuditLogList = {
  total: number;
  limit: number;
  offset: number;
  items: AdminAuditLogItem[];
};

export type PollerHealthCycleSummary = {
  total_cycles: number;
  degraded_cycles: number;
  degraded_rate: number;
  avg_duration_ms: number | null;
  last_error: string | null;
  last_cycle_at: string | null;
};

export type PollerHealth = {
  cycle_summary: PollerHealthCycleSummary;
  lock_held: boolean | null;
  backfill_enabled: boolean;
  backfill_lookback_hours: number;
  backfill_interval_minutes: number;
  clv_enabled: boolean;
  kpi_enabled: boolean;
  recent_errors: string[];
};

export type AdminBackfillTriggerResult = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  reason: string;
  lookback_hours: number;
  max_games: number;
  games_scanned: number;
  games_backfilled: number;
  games_skipped: number;
  errors: number;
};

export type AdminAlertReplayResult = {
  action_id: string;
  acted_at: string;
  actor_user_id: string;
  reason: string;
  signal_id: string;
  signal_type: string;
  event_id: string;
  sent: number;
  failed: number;
};

export type OpsTelemetry = {
  period_days: number;
  total_alerts_sent: number;
  total_alerts_failed: number;
  alert_failure_rate: number;
  backfill_enabled: boolean;
  backfill_lookback_hours: number;
  total_requests_used: number;
  avg_requests_remaining: number | null;
  latest_requests_remaining: number | null;
  latest_requests_limit: number | null;
  projected_daily_burn: number | null;
  total_cycles: number;
  degraded_cycles: number;
  degraded_rate: number;
  avg_cycle_duration_ms: number | null;
  feature_flags: Record<string, boolean>;
};

export type StaleAdminItem = {
  user_id: string;
  email: string;
  admin_role: string | null;
  last_login_at: string | null;
  days_since_login: number | null;
};

export type StaleAdminList = {
  threshold_days: number;
  total: number;
  items: StaleAdminItem[];
};

export type PasswordPolicy = {
  min_length: number;
  require_uppercase: boolean;
  require_lowercase: boolean;
  require_digit: boolean;
  require_special: boolean;
};

export type WebhookOut = {
  id: string;
  url: string;
  description: string | null;
  is_active: boolean;
  secret: string;
};

export type WebhookLogOut = {
  id: string;
  webhook_id: string;
  signal_id: string | null;
  status_code: number | null;
  duration_ms: number;
  error: string | null;
  created_at: string;
};

export type PartnerUsage = {
  month: string;
  request_count: number;
  included_limit: number;
  remaining: number;
  overage_count: number;
  plan_level: string;
};

export type PartnerUsageHistoryRow = {
  period_start: string | null;
  period_end: string | null;
  request_count: number;
  included_limit: number;
  overage_count: number;
};

export type PartnerBillingSummary = {
  plan: {
    plan_code: "api_monthly" | "api_annual" | null;
    api_access_enabled: boolean;
    soft_limit_monthly: number | null;
    overage_enabled: boolean;
    overage_price_cents: number | null;
    overage_unit_quantity: number;
  } | null;
  current_usage: PartnerUsage;
  history: PartnerUsageHistoryRow[];
};
