import test from "node:test";
import assert from "node:assert/strict";

import { formatActionableCardSummary, serializePerformanceFilters } from "./performanceHelpers.js";

test("serializePerformanceFilters includes only defined values", () => {
  const query = serializePerformanceFilters({
    days: 30,
    signal_type: "MOVE",
    market: "spreads",
    min_strength: 70,
    min_samples: undefined,
    limit: 50,
    offset: 0,
  });

  assert.equal(
    query,
    "days=30&signal_type=MOVE&market=spreads&min_strength=70&limit=50&offset=0",
  );
});

test("formatActionableCardSummary formats best vs consensus text", () => {
  const summary = formatActionableCardSummary({
    best_book_key: "draftkings",
    best_line: -2.5,
    best_price: -110,
    consensus_line: -3.0,
    consensus_price: -108,
  });

  assert.equal(summary, "draftkings: -2.5 (-110) vs -3 (-108)");
});

test("formatActionableCardSummary handles null cards", () => {
  assert.equal(formatActionableCardSummary(null), "No actionable card available.");
});
