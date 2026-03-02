from typing import Any, Dict, List


def _format_top_allocation(top: Dict[str, Any]) -> str:
    if not top:
        return "- none"

    signal_type = str(top.get("signal_type", "UNKNOWN"))
    market = str(top.get("market", "UNKNOWN"))
    weight = float(top.get("capital_weight", 0.0))
    pct = int(round(weight * 100.0))
    return f"🟢 {signal_type} {market} — {pct}% weight"


def _format_distribution(allocations: List[Dict[str, Any]]) -> List[str]:
    weighted = [row for row in allocations if float(row.get("capital_weight", 0.0)) > 0.0]
    if not weighted:
        return ["- none"]

    lines: List[str] = []
    for row in weighted:
        signal_type = str(row.get("signal_type", "UNKNOWN"))
        market = str(row.get("market", "UNKNOWN"))
        weight = float(row.get("capital_weight", 0.0))
        lines.append(f"{signal_type} {market} — {weight:.2f}")
    return lines


def _format_excluded(excluded_segments: List[Dict[str, Any]]) -> List[str]:
    if not excluded_segments:
        return ["- none"]

    lines: List[str] = []
    for row in excluded_segments:
        signal_type = str(row.get("signal_type", "UNKNOWN"))
        market = str(row.get("market", "UNKNOWN"))
        reason = str(row.get("reason", "excluded"))
        lines.append(f"{signal_type} {market} ({reason})")
    return lines


def format_discord_summary(report: Dict[str, Any]) -> str:
    date_str = str(report.get("date", "unknown"))
    top = report.get("top_allocation")
    if not isinstance(top, dict):
        top = {}

    allocations = report.get("allocations", [])
    if not isinstance(allocations, list):
        allocations = []

    excluded = report.get("excluded_segments", [])
    if not isinstance(excluded, list):
        excluded = []

    lines = [
        f"Edge Allocation Report — {date_str}",
        "",
        "Top Allocation:",
        _format_top_allocation(top),
        "",
        "Full Distribution:",
        *_format_distribution(allocations),
        "",
        "Excluded:",
        *_format_excluded(excluded),
    ]
    return "\n".join(lines)
