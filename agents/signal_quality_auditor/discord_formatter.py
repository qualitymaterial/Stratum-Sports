from typing import Any, Dict, List


def _icon_for_top_drift(row: Dict[str, Any]) -> str:
    risk = row.get("risk_level")
    classification = row.get("classification")
    if risk == "high":
        return "🔴"
    if classification == "weakening":
        return "🟠"
    if classification == "improving":
        return "🟢"
    return "🟠"


def _format_top_negative_drift(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return ["- none"]

    rendered: List[str] = []
    for row in rows[:3]:
        signal_type = str(row.get("signal_type", "unknown"))
        market = str(row.get("market", "unknown"))
        drift = row.get("drift")
        sample_7d = int(row.get("sample_7d", 0) or 0)
        if drift is None:
            drift_text = "n/a"
        else:
            drift_text = f"{float(drift):.3f}"
        rendered.append(
            f"{_icon_for_top_drift(row)} {signal_type} {market} "
            f"(drift {drift_text}, n={sample_7d})"
        )
    return rendered


def _format_watchlist(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return ["- none"]

    rendered: List[str] = []
    for row in rows:
        signal_type = str(row.get("signal_type", "unknown"))
        market = str(row.get("market", "unknown"))
        pos_rate_30d = row.get("pos_rate_30d")
        sample_30d = int(row.get("sample_30d", 0) or 0)
        if pos_rate_30d is None:
            rate_text = "n/a"
        else:
            rate_text = f"{float(pos_rate_30d):.3f}"
        rendered.append(
            f"🟡 {signal_type} {market} "
            f"(30d rate {rate_text}, n={sample_30d})"
        )
    return rendered


def format_discord_summary(report: dict) -> str:
    date_str = str(report.get("date", "unknown"))
    summary = report.get("summary", {})

    degrading = int(summary.get("degrading_segments_count", 0) or 0)
    high_risk = int(summary.get("high_risk_segments_count", 0) or 0)

    top_3 = summary.get("top_3_worst_drifts", [])
    if not isinstance(top_3, list):
        top_3 = []

    watchlist_segments = report.get("watchlist_segments", [])
    if not isinstance(watchlist_segments, list):
        watchlist_segments = []

    top_lines = _format_top_negative_drift(top_3)
    watchlist_lines = _format_watchlist(watchlist_segments)

    lines = [
        f"Signal Quality Audit — {date_str}",
        "",
        f"Degrading: {degrading}",
        f"High Risk: {high_risk}",
        "",
        "Top Negative Drift:",
        *top_lines,
        "",
        "Watchlist:",
        *watchlist_lines,
    ]
    return "\n".join(lines)
