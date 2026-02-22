import assert from "node:assert/strict";
import test from "node:test";

import { getDashboardConsensusUpdate } from "./dashboardRealtime.js";

const baseCard = {
  event_id: "evt_1",
  home_team: "Boston Celtics",
  away_team: "New York Knicks",
  consensus: {
    spreads: -3.5,
    totals: 221.5,
    h2h_home: -140,
    h2h_away: 120,
  },
};

test("maps spreads update only for home outcome", () => {
  const homeUpdate = getDashboardConsensusUpdate(baseCard, {
    market: "spreads",
    outcome: "Boston Celtics",
    line: -4.0,
    price: -110,
  });
  assert.deepEqual(homeUpdate, { key: "spreads", value: -4.0 });

  const awayIgnored = getDashboardConsensusUpdate(baseCard, {
    market: "spreads",
    outcome: "New York Knicks",
    line: 4.0,
    price: -110,
  });
  assert.equal(awayIgnored, null);
});

test("maps h2h update to side using price", () => {
  const home = getDashboardConsensusUpdate(baseCard, {
    market: "h2h",
    outcome: "Boston Celtics",
    line: null,
    price: -150,
  });
  assert.deepEqual(home, { key: "h2h_home", value: -150 });

  const away = getDashboardConsensusUpdate(baseCard, {
    market: "h2h",
    outcome: "New York Knicks",
    line: null,
    price: 130,
  });
  assert.deepEqual(away, { key: "h2h_away", value: 130 });
});

test("maps totals update using line", () => {
  const totals = getDashboardConsensusUpdate(baseCard, {
    market: "totals",
    outcome: "Over",
    line: 222.0,
    price: -110,
  });
  assert.deepEqual(totals, { key: "totals", value: 222.0 });
});
