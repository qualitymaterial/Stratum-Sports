import logging
import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def wilson_interval_95(pos_rate: float, sample_n: int) -> Tuple[Optional[float], Optional[float]]:
    """Compute Wilson 95% interval for a Bernoulli proportion."""
    if sample_n <= 0:
        return None, None

    p = max(0.0, min(1.0, float(pos_rate)))
    n = float(sample_n)
    z = 1.96
    z2 = z * z

    center = (p + (z2 / (2.0 * n))) / (1.0 + (z2 / n))
    margin = z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n))) / (1.0 + (z2 / n))

    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return low, high


def _escalate_risk(risk_level: str) -> str:
    if risk_level == "low":
        return "medium"
    if risk_level == "medium":
        return "high"
    return "high"


def _downgrade_negative_classification(classification: str, risk_level: str) -> Tuple[str, str]:
    if classification == "degrading":
        return "weakening", "medium"
    if classification == "weakening":
        return "stable", "low"
    return classification, risk_level


def _normalize_rate(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    return float(raw)


def _normalize_avg(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    return float(raw)


class MetricsProcessor:
    def __init__(self, query_results: Dict[str, List[Dict[str, Any]]]):
        self.query_results = query_results

    def process(self) -> Dict[str, Any]:
        # Keyed by (signal_type, market)
        segments: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # 30d segmented stats
        for row in self.query_results.get("clv_30d", []):
            signal_type = str(row["signal_type"])
            market = str(row["market"])
            key = (signal_type, market)
            segments.setdefault(
                key,
                {
                    "signal_type": signal_type,
                    "market": market,
                    "sample_30d": 0,
                    "sample_7d": 0,
                    "pos_rate_30d": None,
                    "pos_rate_7d": None,
                    "avg_clv_30d": None,
                    "avg_clv_7d": None,
                },
            )
            segments[key]["sample_30d"] = int(row["total_samples"])
            segments[key]["pos_rate_30d"] = _normalize_rate(row.get("pos_rate"))
            segments[key]["avg_clv_30d"] = _normalize_avg(row.get("avg_clv"))

        # 7d segmented stats
        for row in self.query_results.get("clv_7d", []):
            signal_type = str(row["signal_type"])
            market = str(row["market"])
            key = (signal_type, market)
            segments.setdefault(
                key,
                {
                    "signal_type": signal_type,
                    "market": market,
                    "sample_30d": 0,
                    "sample_7d": 0,
                    "pos_rate_30d": None,
                    "pos_rate_7d": None,
                    "avg_clv_30d": None,
                    "avg_clv_7d": None,
                },
            )
            segments[key]["sample_7d"] = int(row["total_samples"])
            segments[key]["pos_rate_7d"] = _normalize_rate(row.get("pos_rate"))
            segments[key]["avg_clv_7d"] = _normalize_avg(row.get("avg_clv"))

        # Build per-signal-type structure and deterministic risk logic.
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        top_offenders: List[Dict[str, Any]] = []
        watchlist_segments: List[Dict[str, Any]] = []
        degrading_segments_count = 0
        high_risk_segments_count = 0

        for (signal_type, market), seg in sorted(segments.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            sample_30d = int(seg.get("sample_30d", 0))
            sample_7d = int(seg.get("sample_7d", 0))
            pos_rate_30d = seg.get("pos_rate_30d")
            pos_rate_7d = seg.get("pos_rate_7d")
            avg_clv_30d = seg.get("avg_clv_30d")
            avg_clv_7d = seg.get("avg_clv_7d")
            drift: Optional[float] = None
            wilson_low: Optional[float] = None
            wilson_high: Optional[float] = None

            # Baseline classification
            if sample_30d < 50:
                classification = "insufficient_data"
                risk_level = "low"
            elif pos_rate_7d is None or pos_rate_30d is None:
                classification = "data_gap"
                risk_level = "low"
            else:
                drift = pos_rate_7d - pos_rate_30d
                if drift < -0.05:
                    classification = "degrading"
                    risk_level = "high"
                elif drift < -0.03:
                    classification = "weakening"
                    risk_level = "medium"
                elif drift > 0.05:
                    classification = "improving"
                    risk_level = "low"
                else:
                    classification = "stable"
                    risk_level = "low"

                # Low sample in 7d: reduce negative-alert severity by one level
                if sample_7d < 100:
                    classification, risk_level = _downgrade_negative_classification(classification, risk_level)

                wilson_low, wilson_high = wilson_interval_95(pos_rate_7d, sample_7d)

                # Wilson upper bound guardrail (negative segments only)
                if (
                    classification in {"degrading", "weakening"}
                    and wilson_high is not None
                    and wilson_high < 0.48
                ):
                    risk_level = "high"

            if classification in {"degrading", "weakening"}:
                degrading_segments_count += 1
            if risk_level == "high":
                high_risk_segments_count += 1

            watchlist = (
                sample_30d >= 500
                and pos_rate_30d is not None
                and pos_rate_30d < 0.40
                and classification == "stable"
            )

            market_row = {
                "market": market,
                "sample_30d": sample_30d,
                "sample_7d": sample_7d,
                "pos_rate_30d": round(pos_rate_30d, 6) if pos_rate_30d is not None else None,
                "pos_rate_7d": round(pos_rate_7d, 6) if pos_rate_7d is not None else None,
                "wilson_low_7d": round(wilson_low, 6) if wilson_low is not None else None,
                "wilson_high_7d": round(wilson_high, 6) if wilson_high is not None else None,
                "avg_clv_30d": round(avg_clv_30d, 6) if avg_clv_30d is not None else None,
                "avg_clv_7d": round(avg_clv_7d, 6) if avg_clv_7d is not None else None,
                "classification": classification,
                "risk_level": risk_level,
                "drift": round(drift, 6) if drift is not None else None,
                "watchlist": watchlist,
            }
            grouped.setdefault(signal_type, []).append(market_row)

            if watchlist:
                watchlist_segments.append(
                    {
                        "signal_type": signal_type,
                        "market": market,
                        "pos_rate_30d": round(pos_rate_30d, 6),
                        "sample_30d": sample_30d,
                    }
                )

            if classification in {"degrading", "weakening"}:
                reason = (
                    f"drift={drift:.4f} (7d={pos_rate_7d:.4f}, 30d={pos_rate_30d:.4f}), "
                    f"sample_7d={sample_7d}"
                )
                top_offenders.append(
                    {
                        "signal_type": signal_type,
                        "market": market,
                        "drift": round(drift, 6),
                        "sample_7d": sample_7d,
                        "classification": classification,
                        "risk_level": risk_level,
                        "reason": reason,
                    }
                )

        top_offenders.sort(key=lambda row: row["drift"])
        top_3_worst_drifts = top_offenders[:3]

        signals = [
            {
                "signal_type": signal_type,
                "markets": sorted(markets, key=lambda row: row["market"]),
            }
            for signal_type, markets in sorted(grouped.items(), key=lambda kv: kv[0])
        ]

        summary = {
            "total_signal_types": len(signals),
            "degrading_segments_count": degrading_segments_count,
            "high_risk_segments_count": high_risk_segments_count,
            "top_3_worst_drifts": top_3_worst_drifts,
        }

        return {
            "date": str(date.today()),
            "summary": summary,
            "signals": signals,
            "top_offenders": top_offenders,
            "watchlist_segments": sorted(
                watchlist_segments,
                key=lambda row: (row["pos_rate_30d"], -row["sample_30d"], row["signal_type"], row["market"]),
            ),
        }
