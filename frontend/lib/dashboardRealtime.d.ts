import type { DashboardCard } from "@/lib/types";
import type { WebSocketMessage } from "@/lib/useOddsSocket";

type DashboardConsensusKey = "spreads" | "totals" | "h2h_home" | "h2h_away";

export function getDashboardConsensusUpdate(
  card: Pick<DashboardCard, "home_team" | "away_team">,
  msg: Pick<WebSocketMessage, "market" | "outcome" | "line" | "price">,
): { key: DashboardConsensusKey; value: number } | null;
