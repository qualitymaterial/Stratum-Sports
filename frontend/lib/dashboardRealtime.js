export function getDashboardConsensusUpdate(card, msg) {
  if (!card || !msg) {
    return null;
  }

  if (msg.market === "spreads") {
    if (msg.outcome !== card.home_team || msg.line == null) {
      return null;
    }
    return { key: "spreads", value: msg.line };
  }

  if (msg.market === "totals") {
    if (msg.line == null) {
      return null;
    }
    return { key: "totals", value: msg.line };
  }

  if (msg.market === "h2h") {
    if (msg.price == null) {
      return null;
    }
    if (msg.outcome === card.home_team) {
      return { key: "h2h_home", value: msg.price };
    }
    if (msg.outcome === card.away_team) {
      return { key: "h2h_away", value: msg.price };
    }
  }

  return null;
}
