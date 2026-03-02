import math
from typing import Any, Dict, List


def wilson_interval_95(pos_rate: float, sample_n: int) -> tuple[float, float]:
    if sample_n <= 0:
        return 0.0, 0.0

    p = max(0.0, min(1.0, float(pos_rate)))
    n = float(sample_n)
    z = 1.96
    z2 = z * z

    center = (p + (z2 / (2.0 * n))) / (1.0 + (z2 / n))
    margin = z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n))) / (1.0 + (z2 / n))

    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return low, high


def _risk_tier(drift: float, wilson_low_30d: float, sample_30d: int) -> str:
    if drift < -0.05:
        return "degrading"
    if wilson_low_30d < 0.47:
        return "fragile"
    if sample_30d < 200:
        return "thin"
    return "healthy"


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _excluded_reason(segment: Dict[str, Any]) -> str:
    risk = segment["risk"]
    if risk == "thin":
        return "thin sample"
    if risk in {"degrading", "fragile"}:
        return risk
    if not segment["eligible"]:
        return "ineligible"
    return "non-positive edge"


def _rounded_weight_distribution(segments: List[Dict[str, Any]]) -> None:
    if not segments:
        return

    sorted_segments = sorted(
        segments,
        key=lambda s: (-float(s["edge_score"]), s["signal_type"], s["market"]),
    )
    edge_total = sum(float(s["edge_score"]) for s in sorted_segments)
    if edge_total <= 0:
        return

    total_units = 1_000_000
    allocated_units = 0

    for seg in sorted_segments[:-1]:
        raw_weight = float(seg["edge_score"]) / edge_total
        units = int(raw_weight * total_units)
        seg["capital_weight"] = units / total_units
        allocated_units += units

    final_units = max(0, total_units - allocated_units)
    sorted_segments[-1]["capital_weight"] = final_units / total_units


def build_allocation_report(rows: List[Dict[str, Any]], report_date: str) -> Dict[str, Any]:
    allocations: List[Dict[str, Any]] = []

    for row in rows:
        signal_type = str(row.get("signal_type") or "UNKNOWN")
        market = str(row.get("market") or "UNKNOWN")

        sample_30d = int(row.get("sample_30d") or 0)
        sample_7d = int(row.get("sample_7d") or 0)

        pos_rate_30d = _safe_float(row.get("pos_rate_30d"))
        pos_rate_7d = _safe_float(row.get("pos_rate_7d"))
        avg_clv_30d = _safe_float(row.get("avg_clv_30d"))
        avg_clv_7d = _safe_float(row.get("avg_clv_7d"))

        drift = pos_rate_7d - pos_rate_30d
        wilson_low_30d, _wilson_high_30d = wilson_interval_95(pos_rate_30d, sample_30d)

        base_edge = pos_rate_30d - 0.50
        if drift > 0:
            stability_bonus = 0.02
        elif drift < -0.03:
            stability_bonus = -0.02
        else:
            stability_bonus = 0.0

        confidence_multiplier = min(1.0, sample_30d / 1000.0)
        wilson_floor_penalty = -0.03 if wilson_low_30d < 0.48 else 0.0
        edge_score = round(
            (base_edge * confidence_multiplier) + stability_bonus + wilson_floor_penalty,
            6,
        )

        risk = _risk_tier(drift, wilson_low_30d, sample_30d)
        eligible = pos_rate_30d > 0.50 and sample_30d >= 200

        allocations.append(
            {
                "signal_type": signal_type,
                "market": market,
                "edge_score": edge_score,
                "capital_weight": 0.0,
                "risk": risk,
                "sample_30d": sample_30d,
                "sample_7d": sample_7d,
                "pos_rate_30d": round(pos_rate_30d, 6),
                "pos_rate_7d": round(pos_rate_7d, 6),
                "avg_clv_30d": round(avg_clv_30d, 6),
                "avg_clv_7d": round(avg_clv_7d, 6),
                "drift": round(drift, 6),
                "wilson_low_30d": round(wilson_low_30d, 6),
                "eligible": eligible,
            }
        )

    positive_allocations = [
        seg
        for seg in allocations
        if seg["eligible"] and float(seg["edge_score"]) > 0
    ]
    _rounded_weight_distribution(positive_allocations)

    allocations_sorted = sorted(
        allocations,
        key=lambda s: (-float(s["capital_weight"]), -float(s["edge_score"]), s["signal_type"], s["market"]),
    )

    allocation_rows = [
        {
            "signal_type": seg["signal_type"],
            "market": seg["market"],
            "edge_score": seg["edge_score"],
            "capital_weight": round(float(seg["capital_weight"]), 6),
            "risk": seg["risk"],
            "pos_rate_30d": seg["pos_rate_30d"],
            "sample_30d": seg["sample_30d"],
        }
        for seg in allocations_sorted
    ]

    excluded_segments = [
        {
            "signal_type": seg["signal_type"],
            "market": seg["market"],
            "reason": _excluded_reason(seg),
        }
        for seg in allocations_sorted
        if float(seg["capital_weight"]) <= 0.0
    ]

    top_allocation = {}
    for seg in allocation_rows:
        if float(seg["capital_weight"]) > 0.0:
            top_allocation = seg
            break

    return {
        "date": report_date,
        "allocations": allocation_rows,
        "excluded_segments": excluded_segments,
        "top_allocation": top_allocation,
    }
