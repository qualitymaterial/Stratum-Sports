# Signal Quality Auditor (V2)

Read-only internal auditor for CLV performance drift by `signal_type` and `market`.

## What V2 Adds
- Per-market segmentation (`spreads`, `totals`, `h2h` when present).
- Deterministic Wilson 95% confidence interval on 7d positive CLV rate.
- Deterministic risk logic with low-sample dampening.
- Top offenders list for the worst degrading/weakening segments.
- Commentary-only LLM layer (no LLM math, no metric mutation).

## Data Model Expectations
The agent introspects the CLV table and expects these columns when available:
- `signal_type`
- `market`
- `computed_at` (or equivalent timestamp)
- `clv_line` and/or `clv_prob`

If both `clv_line` and `clv_prob` exist, V2 uses:
- `COALESCE(clv_line, clv_prob)` for value and positive-rate aggregation.

## Deterministic Metrics
For each `(signal_type, market)` segment:
- `sample_30d`, `sample_7d`
- `pos_rate_30d`, `pos_rate_7d`
- `avg_clv_30d`, `avg_clv_7d`
- `wilson_low_7d`, `wilson_high_7d`
- `classification`, `risk_level`

### Wilson 95% Interval
Implemented in pure Python in `metrics.py`:

Given `p=pos_rate_7d`, `n=sample_7d`, `z=1.96`:

- `center = (p + z^2/(2n)) / (1 + z^2/n)`
- `margin = z * sqrt((p*(1-p)/n) + (z^2/(4n^2))) / (1 + z^2/n)`
- `wilson_low = center - margin`
- `wilson_high = center + margin`

### Risk & Classification Rules
For each market segment:

1. If `sample_30d < 50`:
- `classification = insufficient_data`
- `risk_level = low`

2. Else compute `drift = pos_rate_7d - pos_rate_30d`:
- `drift < -0.05` -> `degrading`, `high`
- `drift < -0.03` -> `weakening`, `medium`
- `drift > 0.05` -> `improving`, `low`
- otherwise -> `stable`, `low`

3. Noise dampener:
- If `sample_7d < 100`, downgrade negative severity by one step:
  - `degrading -> weakening`
  - `weakening -> stable`

4. Confidence guardrail:
- If `wilson_high_7d < 0.48`, escalate risk by one level (`low->medium->high`).

## Output
Saved to:
- `agents/signal_quality_auditor/out/quality_report_v2_YYYY-MM-DD.json`

Top-level report fields include:
- `summary`
- `signals` (per signal type with nested `markets`)
- `top_offenders`
- `executive_interpretation`
- `optimization_suggestions`

## Run
```bash
python agents/signal_quality_auditor/main.py
```

## Terminal Summary
On each run, V2 prints:
- total signal types
- degrading segments count
- high risk segments count
- top 3 worst drifts

## Scheduling
Example cron entry (daily at 9:00 AM):
```bash
0 9 * * * cd /path/to/stratum-sports && python3 agents/signal_quality_auditor/main.py >> agents/signal_quality_auditor/audit.log 2>&1
```
