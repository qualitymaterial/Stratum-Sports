from typing import Any, Dict
from app.core.config import get_settings

def compute_kalshi_skew_gate(skew: float | None) -> Dict[str, Any]:
    """
    Compute Kalshi liquidity skew gates.
    """
    settings = get_settings()
    
    res = {
        "kalshi_liquidity_skew": skew,
        "kalshi_gate_threshold": settings.kalshi_skew_gate_threshold,
        "kalshi_gate_mode": settings.kalshi_skew_gate_mode,
        "kalshi_skew_bucket": None,
        "kalshi_gate_pass": None,
    }
    
    if skew is None:
        return res
        
    bucket = "A: <0.55"
    if skew < 0.55:
        bucket = "A: <0.55"
    elif skew < 0.60:
        bucket = "B: 0.55-0.60"
    elif skew <= 0.65:
        bucket = "C: 0.60-0.65"
    else:
        bucket = "D: >0.65"
        
    res["kalshi_skew_bucket"] = bucket
    res["kalshi_gate_pass"] = skew >= settings.kalshi_skew_gate_threshold
    
    return res
