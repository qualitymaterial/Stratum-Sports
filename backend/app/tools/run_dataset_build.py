from __future__ import annotations

import argparse
import subprocess
import sys


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NBA historical backfill then dataset sanity diagnostics")
    parser.add_argument("--start", default="2026-02-20T00:00:00Z", help="Backfill start (ISO8601 UTC)")
    parser.add_argument("--end", default="2026-02-23T00:00:00Z", help="Backfill end (ISO8601 UTC)")
    parser.add_argument("--sport_key", default="basketball_nba", help="Sport key")
    parser.add_argument("--markets", default="spreads,totals,h2h", help="Comma-separated markets")
    parser.add_argument("--max_events", type=int, default=50, help="Maximum events to process")
    parser.add_argument("--max_requests", type=int, default=1200, help="Max request budget")
    parser.add_argument(
        "--min_requests_remaining",
        type=int,
        default=150,
        help="Stop when remaining requests are at or below this threshold",
    )
    parser.add_argument("--history_step_minutes", type=int, default=120, help="Historical sampling interval in minutes")
    return parser


def _run_phase(header: str, cmd: list[str]) -> int:
    print(header, flush=True)
    print(" ".join(cmd), flush=True)
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    python = sys.executable
    backfill_cmd = [
        python,
        "-m",
        "app.tools.backfill_history",
        "--start",
        str(args.start),
        "--end",
        str(args.end),
        "--sport_key",
        str(args.sport_key),
        "--markets",
        str(args.markets),
        "--max_events",
        str(int(args.max_events)),
        "--max_requests",
        str(int(args.max_requests)),
        "--min_requests_remaining",
        str(int(args.min_requests_remaining)),
        "--history_step_minutes",
        str(int(args.history_step_minutes)),
    ]

    backfill_rc = _run_phase("=== BACKFILL RUN ===", backfill_cmd)
    if backfill_rc != 0:
        return backfill_rc

    sanity_cmd = [python, "-m", "app.tools.dataset_sanity"]
    sanity_rc = _run_phase("=== DATASET SANITY ===", sanity_cmd)
    return sanity_rc


if __name__ == "__main__":
    raise SystemExit(main())
