# Exchange Intelligence

The Exchange Intelligence layer processes prediction market data (Kalshi) as an additive signal source for traditional sportsbook data. It does not replace legacy lines but provides context on capital flow to identify market disparities.

## Definitions

### Canonical Alignment
The bridging mechanism mapping a fragmented traditional sports event to a discrete prediction market contract.

### Exchange Quote Events
The raw time-series observations of probability and liquidity on the exchange platform.

### Cross-market Divergence
A computed state where the implied probability of a sportsbook outcome substantially deviates from the exchange probability.

### Liquidity Skew
The measured percentage of directional capital imbalance on a specific contract (`kalshi_liquidity_skew`).

## Contextualizing System State

The system observes a 3.5% skew incidence. This is a healthy distribution. Extreme liquidity imbalances should be rare. Elevated skew incidence indicates a flawed threshold or a broken market.

The magnitude range observed (+60.00% to +88.00%) is highly meaningful. It indicates substantial capital commitment on the exchange. However, this is observational data and not a guaranteed edge.

## UI Badge Display Rules

### EXCHANGE CONFIRMED
Condition: A traditional value signal aligns directionally with exchange probability pricing.

### DIVERGENCE
Condition: A traditional value signal opposes exchange probability pricing by a specified margin.

### LIQUIDITY SKEW
Condition: `kalshi_liquidity_skew` exceeds the predefined baseline threshold.

### STEAM / MOVE
Condition: Unchanged from core multi-book consensus shifting.

## Positioning Claims

### Safe Positioning Claims
- Observes capital allocation on regulated prediction markets.
- Identifies disparities between legacy sportsbooks and prediction exchanges.
- Computes liquidity skew based on order book depth.

### Avoid Claims
- Do not claim predictive certainty.
- Do not guarantee positive expected value (EV) or profits.
- Do not characterize exchange intelligence as a primary betting unit.
