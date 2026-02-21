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
  signal_type: "MOVE" | "KEY_CROSS" | "MULTIBOOK_SYNC";
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
