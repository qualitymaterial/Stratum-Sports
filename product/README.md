# Product Source of Truth

Stratum is an institutional-grade sports market intelligence layer. It structures disparate, asynchronous global sports betting data and exchange liquidity into an actionable, unified event-driven data model.

This is a documentation-only directory. It has no runtime impact on the application.

## Current System State (Local Proof)

- Canonical Alignments (Kalshi Mappings): 31
- Exchange Quote Events (Raw Data): 34
- Total Signals: 65,024
- Signals with kalshi_liquidity_skew: 2,283

## Production Proof

Direct DB query over SSH demonstrated the following:
- Sample: 30 most recent betting signals enriched with Kalshi liquidity skew
- All rows: Gate Pass = True
- Skew range observed: +60.00% to +88.00%
- Markets observed: spreads, totals, h2h
- Signal types observed: DISLOCATION, MOVE, KEY_CROSS

## Signal Families

### Movement / Steam
Tracks material price or line movement across significant sportsbooks within a condensed time window.

### Cross-market Divergence
Highlights latency or pricing inconsistency between legacy sportsbooks and modern exchange platforms.

### Liquidity Skew
Measures the directional imbalance of capital on prediction markets, applied directly to traditional sports betting lines.

### Validation (CLV / close capture)
Tracks the closing line to validate the expected value of generated signals at market closure.

## UI Badges (Minimal Set)

- **EXCHANGE CONFIRMED**: The exchange market pricing firmly aligns with the identified sportsbook inefficiency.
- **DIVERGENCE**: The traditional sportsbook line materially conflicts with the implied probability of the exchange.
- **LIQUIDITY SKEW**: Capital allocation on the exchange is heavily weighted toward one side of the market.
- **STEAM / MOVE**: Broad market consensus is rapidly shifting the price or line for a specific outcome.

## Where This Is Used

- Engineering: Maintains consistency of data mapping and ingestion objectives.
- Marketing: Aligns product messaging with factual system capabilities.
- Support: Clarifies product features and data sources for end-users.

## References

- [Exchange Intelligence](./features/exchange-intelligence.md)
- [Architecture diagrams](./diagrams/)
