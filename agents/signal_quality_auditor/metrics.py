import logging
from typing import Dict, Any, List, Optional, cast

logger = logging.getLogger(__name__)

class MetricsProcessor:
    def __init__(self, query_results: Dict[str, List[Dict[str, Any]]]):
        self.query_results = query_results

    def process(self) -> Dict[str, Any]:
        # 1. Pivot results by signal type
        # Results structure: {signal_type: {attr: val}}
        master_signals: Dict[str, Dict[str, Any]] = {}
        
        # Process 30d stats
        res_30d = self.query_results.get("clv_30d", [])
        for r in res_30d:
            stype = str(r["signal_type"])
            master_signals[stype] = {
                "signal_type": stype,
                "sample_30d": int(r["total_samples"]),
                "pos_rate_30d": float(r["pos_rate"]) if r["pos_rate"] is not None else 0.0,
                "avg_clv_30d": float(r["avg_clv"]) if r["avg_clv"] is not None else 0.0,
                "pos_rate_7d": None,
                "avg_clv_7d": None,
                "sample_7d": 0
            }
            
        # Process 7d stats
        res_7d = self.query_results.get("clv_7d", [])
        for r in res_7d:
            stype = str(r["signal_type"])
            if stype not in master_signals:
                master_signals[stype] = {
                    "signal_type": stype,
                    "sample_30d": 0,
                    "pos_rate_30d": None,
                    "avg_clv_30d": None
                }
            master_signals[stype].update({
                "pos_rate_7d": float(r["pos_rate"]) if r["pos_rate"] is not None else 0.0,
                "avg_clv_7d": float(r["avg_clv"]) if r["avg_clv"] is not None else 0.0,
                "sample_7d": int(r["total_samples"])
            })

        processed_signals: List[Dict[str, Any]] = []
        summary = {
            "total_signal_types": 0,
            "degrading_count": 0,
            "improving_count": 0,
            "stable_count": 0
        }

        # 2. Apply deterministic rules
        for stype, data in master_signals.items():
            summary["total_signal_types"] += 1
            
            sample_30d = data.get("sample_30d", 0)
            rate_30d = data.get("pos_rate_30d")
            rate_7d = data.get("pos_rate_7d")
            
            # Defaults
            classification = "stable"
            risk_level = "low"
            
            if sample_30d is not None and int(sample_30d) < 50:
                classification = "insufficient_data"
            elif rate_7d is None or rate_30d is None:
                classification = "insufficient_data"
            else:
                # Deterministic float comparison
                diff = float(cast(float, rate_7d)) - float(cast(float, rate_30d))
                if diff < -0.05:
                    classification = "degrading"
                    summary["degrading_count"] += 1
                elif diff > 0.05:
                    classification = "improving"
                    summary["improving_count"] += 1
                else:
                    classification = "stable"
                    summary["stable_count"] += 1
            
            # Risk level (High if pos_rate_7d < 48%)
            if rate_7d is not None and float(cast(float, rate_7d)) < 0.48:
                risk_level = "high"
            elif classification == "degrading":
                risk_level = "medium"
            
            # Assemble record
            processed_signals.append({
                "signal_type": stype,
                "sample_30d": sample_30d,
                "pos_rate_30d": rate_30d,
                "pos_rate_7d": rate_7d,
                "avg_clv_30d": data.get("avg_clv_30d"),
                "avg_clv_7d": data.get("avg_clv_7d"),
                "classification": classification,
                "risk_level": risk_level
            })

        return {
            "summary": summary,
            "signals": processed_signals
        }
