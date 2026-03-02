# Edge Allocator Agent

Read-only capital allocation recommendation layer for Stratum Sports.

This agent does not execute trades. It only outputs allocation distribution recommendations.

## Scope

- Ranks signal segments by statistical edge.
- Scores capital allocation priority.
- Penalizes unstable or degrading segments.
- Outputs recommended capital weights.
- Produces structured JSON and a Discord summary.

## Data Inputs (Read-Only)

- `clv_records`
- `signals`
- `signals.metadata` is available via join, with `signal_type`/`market` fallback sourced from `signals` if needed.

Segment keys:

- `signal_type`
- `market`

Windows:

- `30d`
- `7d`

CLV value source:

- `COALESCE(clv_records.clv_line, clv_records.clv_prob)`

## Deterministic Metrics

Per `(signal_type, market)`:

- `sample_30d`
- `sample_7d`
- `pos_rate_30d`
- `pos_rate_7d`
- `avg_clv_30d`
- `avg_clv_7d`
- `drift = pos_rate_7d - pos_rate_30d`
- `wilson_low_30d`/`wilson_high_30d` (95% Wilson interval on 30d positive rate)

## Edge Score Math

Given:

- `base_edge = pos_rate_30d - 0.50`
- `stability_bonus`:
  - `+0.02` if `drift > 0`
  - `-0.02` if `drift < -0.03`
  - `0` otherwise
- `confidence_multiplier = min(1.0, sample_30d / 1000)`
- `wilson_floor_penalty = -0.03 if wilson_low_30d < 0.48 else 0`

Then:

`edge_score = (base_edge * confidence_multiplier) + stability_bonus + wilson_floor_penalty`

`edge_score` is rounded to 6 decimals.

## Capital Allocation Logic

Eligible segment criteria:

- `pos_rate_30d > 0.50`
- `sample_30d >= 200`

Allocation:

- Only eligible segments with positive `edge_score` receive weight.
- Positive eligible `edge_score` values are normalized so weights sum to `1.0`.
- Segments with non-positive `edge_score` have `capital_weight = 0`.

## Risk Tiers

Applied in this precedence order:

1. `degrading` if `drift < -0.05`
2. `fragile` if `wilson_low_30d < 0.47`
3. `thin` if `sample_30d < 200`
4. `healthy` otherwise

## Output

Saved JSON:

- `agents/edge_allocator/out/edge_allocation_YYYY-MM-DD.json`

Shape:

```json
{
  "date": "YYYY-MM-DD",
  "allocations": [
    {
      "signal_type": "MOVE",
      "market": "spreads",
      "edge_score": 0.024158,
      "capital_weight": 0.38,
      "risk": "healthy",
      "pos_rate_30d": 0.541,
      "sample_30d": 812
    }
  ],
  "excluded_segments": [
    {
      "signal_type": "DISLOCATION",
      "market": "totals",
      "reason": "fragile"
    }
  ],
  "top_allocation": {
    "signal_type": "MOVE",
    "market": "spreads",
    "edge_score": 0.024158,
    "capital_weight": 0.38,
    "risk": "healthy",
    "pos_rate_30d": 0.541,
    "sample_30d": 812
  }
}
```

Discord text format:

```text
Edge Allocation Report — YYYY-MM-DD

Top Allocation:
🟢 MOVE spreads — 38% weight

Full Distribution:
MOVE spreads — 0.38
STEAM totals — 0.27
DISLOCATION h2h — 0.18
LLM_SIGNAL spreads — 0.17

Excluded:
DISLOCATION totals (fragile)
MOVE h2h (thin sample)
```

## Run

```bash
python agents/edge_allocator/main.py
```

## Environment

Copy and edit local env:

```bash
cp agents/edge_allocator/.env.example agents/edge_allocator/.env
```

Required:

- `DATABASE_URL` (use read-only credentials)

Optional:

- `DISCORD_WEBHOOK_URL`

## Weekly Cron Template

Sunday at 09:00 UTC:

```bash
0 9 * * 0 cd /opt/stratum-sports && /opt/stratum-sports/.venv/bin/python agents/edge_allocator/main.py >> edge_allocator.log 2>&1
```
