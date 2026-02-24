export type User = {
  id: string;
  email: string;
  tier: "free" | "pro";
  is_admin: boolean;
  created_at: string;
};

export type SportKey = "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl";

export type Signal = {
  id: string;
  event_id: string;
  market: string;
  signal_type: "MOVE" | "KEY_CROSS" | "MULTIBOOK_SYNC" | "DISLOCATION" | "STEAM";
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
  direction: string;
  strength_score: number;
  books_affected: number;
  window_minutes: number;
  created_at: string;
  outcome_name: string | null;
  book_key: string | null;
  delta: number | null;
  dispersion: number | null;
  alert_decision: "sent" | "hidden" | string;
  alert_reason: string;
  metadata: Record<string, unknown>;
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
  delta_type: string;
  books_considered: number;
  freshness_seconds: number | null;
  freshness_bucket: "fresh" | "aging" | "stale" | string;
  execution_rank: number;
  clv_prior_samples: number | null;
  clv_prior_pct_positive: number | null;
  opportunity_score: number;
  opportunity_status: "actionable" | "monitor" | "stale" | string;
  reason_tags: string[];
  actionable_reason: string;
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
};
