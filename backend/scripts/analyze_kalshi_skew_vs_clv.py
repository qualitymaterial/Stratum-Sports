import asyncio
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from statistics import mean, median

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.signal import Signal
from app.models.clv_record import ClvRecord

logging.basicConfig(level=logging.ERROR)

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def z_test_proportions(k1, n1, k2, n2):
    if n1 == 0 or n2 == 0:
        return None, None
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p2 - p1) / se
    p_value = 2 * (1 - norm_cdf(abs(z)))
    return z, p_value

def wilson_score_interval(k, n, confidence=0.95):
    if n == 0:
        return 0.0, 0.0
    z = 1.96 # for 95%
    p = k / n
    denominator = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    pm = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))
    lower = (center - pm) / denominator
    upper = (center + pm) / denominator
    return max(0.0, lower), min(1.0, upper)

def bucket_skew(skew):
    if skew < 0.55:
        return "A: <0.55"
    if skew < 0.60:
        return "B: 0.55-0.60"
    if skew <= 0.65:
        return "C: 0.60-0.65"
    return "D: >0.65"

def analyze_dataset(rows, name):
    if not rows:
        return {}
    
    buckets = {
        "A: <0.55": [],
        "B: 0.55-0.60": [],
        "C: 0.60-0.65": [],
        "D: >0.65": []
    }
    
    for r in rows:
        buckets[bucket_skew(r["skew"])].append(r)
        
    res = {}
    for b_name, items in buckets.items():
        n = len(items)
        if n == 0:
            res[b_name] = {"n": 0}
            continue
        k = sum(1 for x in items if x["pos"])
        deltas = [x["delta"] for x in items]
        lower, upper = wilson_score_interval(k, n)
        
        res[b_name] = {
            "n": n,
            "positive_rate": k / n,
            "ci_95_lower": lower,
            "ci_95_upper": upper,
            "avg_clv_delta": mean(deltas),
            "median_clv_delta": median(deltas)
        }
    
    # Also add the ge aggregates requested (>=0.60, >0.65 are mostly covered but D is >0.65 and C+D is >=0.60, handled elsewhere)
        
    all_n = len(rows)
    all_k = sum(1 for x in rows if x["pos"])
    all_deltas = [x["delta"] for x in rows]
    res["overall"] = {
        "n": all_n,
        "positive_rate": all_k / all_n if all_n > 0 else 0,
        "avg_clv_delta": mean(all_deltas) if all_n > 0 else 0,
        "median_clv_delta": median(all_deltas) if all_n > 0 else 0,
    }
    
    return res

async def main():
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    
    async with AsyncSessionLocal() as db:
        stmt = (
            select(
                Signal.id,
                Signal.created_at,
                Signal.signal_type,
                Signal.metadata_json,
                ClvRecord.clv_prob
            )
            .select_from(Signal)
            .join(ClvRecord, Signal.id == ClvRecord.signal_id)
            .where(
                and_(
                    Signal.created_at >= thirty_days_ago,
                    ClvRecord.clv_prob.is_not(None)
                )
            )
        )
        result = await db.execute(stmt)
        raw_rows = result.all()
        
    data = []
    now = datetime.now(UTC)
    for row in raw_rows:
        meta = row.metadata_json or {}
        skew = meta.get("exchange_liquidity_skew")
        if skew is not None:
            clv_delta = float(row.clv_prob)
            pos = clv_delta > 0
            # in days
            age_days = (now - row.created_at).total_seconds() / 86400.0
            data.append({
                "skew": float(skew),
                "pos": pos,
                "delta": clv_delta,
                "type": row.signal_type,
                "age_days": age_days
            })
            
    windows = {
        "30d": data,
        "14d": [d for d in data if d["age_days"] <= 14],
        "7d": [d for d in data if d["age_days"] <= 7]
    }
    
    output = {
        "generated_at": now.isoformat(),
        "windows": {},
        "tests": {},
        "notes": [
            "Assumed exchange_liquidity_skew is stored in `Signal.metadata_json`.",
            "Using wilson score internal for 95% CI of proportions.",
            "Baseline for significance testing is <0.60 (Buckets A & B).",
            "clv_delta driven directly by finalized `clv_prob` in records."
        ]
    }
    
    for w_name, w_data in windows.items():
        w_res = analyze_dataset(w_data, w_name)
        
        types = set(d["type"] for d in w_data)
        by_type = {}
        for t in types:
            t_data = [d for d in w_data if d["type"] == t]
            by_type[t] = analyze_dataset(t_data, f"{w_name}_{t}")
            
        output["windows"][w_name] = {
            "overall": w_res.get("overall", {}),
            "by_bucket": w_res,
            "by_signal_type": by_type
        }
        
    d30 = windows["30d"]
    baseline = [d for d in d30 if d["skew"] < 0.60]
    ge_060 = [d for d in d30 if d["skew"] >= 0.60]
    gt_065 = [d for d in d30 if d["skew"] > 0.65]
    
    b_k = sum(1 for d in baseline if d["pos"])
    b_n = len(baseline)
    
    ge_k = sum(1 for d in ge_060 if d["pos"])
    ge_n = len(ge_060)
    
    gt_k = sum(1 for d in gt_065 if d["pos"])
    gt_n = len(gt_065)
    
    z1, p1 = z_test_proportions(b_k, b_n, ge_k, ge_n)
    z2, p2 = z_test_proportions(b_k, b_n, gt_k, gt_n)
    
    output["tests"]["baseline_vs_ge_060"] = {
        "p_value": p1 if p1 is not None else 1.0,
        "z": z1 if z1 is not None else 0.0,
        "n_baseline": b_n,
        "n_ge_060": ge_n
    }
    output["tests"]["baseline_vs_gt_065"] = {
        "p_value": p2 if p2 is not None else 1.0,
        "z": z2 if z2 is not None else 0.0,
        "n_baseline": b_n,
        "n_gt_065": gt_n 
    }
    
    json_path = "kalshi_skew_analysis.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
        
    print("\n=== KALSHI SKEW VS CLV ANALYSIS (30d) ===")
    print(f"{'Bucket':<15} | {'N':<6} | {'% Pos':<7} | {'95% CI':<20} | {'Avg Δ':<8} | {'Med Δ':<8}")
    print("-" * 75)
    for b in ["A: <0.55", "B: 0.55-0.60", "C: 0.60-0.65", "D: >0.65"]:
        stats = output["windows"]["30d"]["by_bucket"].get(b, {})
        if not stats or stats.get("n", 0) == 0:
            continue
        
        warn = "*" if stats["n"] < 100 else " "
        n_str = f"{stats['n']}{warn}"
        pos_str = f"{stats['positive_rate']*100:.1f}%"
        ci_str = f"[{stats['ci_95_lower']*100:.1f}%, {stats['ci_95_upper']*100:.1f}%]"
        avg_str = f"{stats.get('avg_clv_delta',0):.4f}"
        med_str = f"{stats.get('median_clv_delta',0):.4f}"
        
        print(f"{b:<15} | {n_str:<6} | {pos_str:<7} | {ci_str:<20} | {avg_str:<8} | {med_str:<8}")
        
    print("\n* Warning: n < 100, results may be unstable.")
    
    print("\n=== SIGNIFICANCE TESTS ===")
    res1 = output["tests"]["baseline_vs_ge_060"]
    print(f"Baseline (<0.60) vs >=0.60 : Z={res1['z']:.2f}, p={res1['p_value']:.4e} | N_base={res1['n_baseline']}, N_treat={res1['n_ge_060']}")
    
    res2 = output["tests"]["baseline_vs_gt_065"]
    print(f"Baseline (<0.60) vs >0.65  : Z={res2['z']:.2f}, p={res2['p_value']:.4e} | N_base={res2['n_baseline']}, N_treat={res2['n_gt_065']}")
    
    print(f"\nAnalysis saved to {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
