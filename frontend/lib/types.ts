export type User = {
  id: string;
  email: string;
  tier: "free" | "pro";
  is_admin: boolean;
  created_at: string;
};

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
  strength_score: number;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type DashboardCard = {
  event_id: string;
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
  thresholds: Record<string, unknown>;
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
  metadata: Record<string, unknown>;
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
  is_stale: boolean;
  books_considered: number;
  quotes: ActionableBookQuote[];
};
