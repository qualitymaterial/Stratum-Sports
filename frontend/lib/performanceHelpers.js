export function serializePerformanceFilters(filters) {
  const params = new URLSearchParams();
  const append = (key, value) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    params.set(key, String(value));
  };

  append("days", filters?.days);
  append("signal_type", filters?.signal_type);
  append("market", filters?.market);
  append("min_strength", filters?.min_strength);
  append("min_samples", filters?.min_samples);
  append("limit", filters?.limit);
  append("offset", filters?.offset);
  return params.toString();
}

export function formatActionableCardSummary(card) {
  if (!card) {
    return "No actionable card available.";
  }

  const bestValue =
    card.best_line != null ? `${card.best_line} (${card.best_price ?? "-"})` : `${card.best_price ?? "-"}`;
  const consensusValue =
    card.consensus_line != null
      ? `${card.consensus_line} (${card.consensus_price ?? "-"})`
      : `${card.consensus_price ?? "-"}`;

  return `${card.best_book_key ?? "-"}: ${bestValue} vs ${consensusValue}`;
}
