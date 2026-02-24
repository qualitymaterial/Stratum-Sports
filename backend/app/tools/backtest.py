from __future__ import annotations

import argparse
import asyncio
import bisect
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median as stats_median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.tools.backtest_rules import (
    BacktestRuleConfig,
    SimulatedSignal,
    apply_pseudo_clv,
    build_event_replay_data,
    compute_consensus_at_t,
    detect_dislocation_at_t,
    detect_move_at_t,
    detect_multibook_sync_at_t,
    detect_steam_at_t,
    sort_simulated_signals,
)

TIME_BUCKET_ORDER: tuple[str, ...] = ("OPEN", "MID", "LATE", "PRETIP", "UNKNOWN")
SCORE_BAND_ORDER: tuple[str, ...] = ("0-54", "55-74", "75-100")
SCORE_SOURCE_ORDER: tuple[str, ...] = ("composite", "strength_fallback")


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "reports"


def _parse_utc_date(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(tzinfo=UTC)


def _parse_markets(value: str) -> tuple[str, ...]:
    allowed = {"spreads", "totals", "h2h"}
    markets = tuple(part.strip() for part in value.split(",") if part.strip())
    if not markets:
        raise ValueError("At least one market is required")
    invalid = [market for market in markets if market not in allowed]
    if invalid:
        raise ValueError(f"Unsupported market(s): {','.join(sorted(set(invalid)))}")
    return markets


def _build_rule_config(
    *,
    markets: tuple[str, ...],
    lookback_minutes: int,
    min_books: int,
) -> BacktestRuleConfig:
    settings = get_settings()
    return BacktestRuleConfig(
        markets=markets,
        lookback_minutes=max(1, lookback_minutes),
        min_books=max(1, min_books),
        nba_key_numbers=tuple(settings.nba_key_numbers_list),
        dislocation_spread_line_delta=float(settings.dislocation_spread_line_delta),
        dislocation_total_line_delta=float(settings.dislocation_total_line_delta),
        dislocation_ml_implied_prob_delta=float(settings.dislocation_ml_implied_prob_delta),
        dislocation_cooldown_seconds=max(1, int(settings.dislocation_cooldown_seconds)),
        dislocation_max_signals_per_event=max(1, int(settings.dislocation_max_signals_per_event)),
        steam_window_minutes=max(1, int(settings.steam_window_minutes)),
        steam_min_books=max(1, int(settings.steam_min_books)),
        steam_min_move_spread=float(settings.steam_min_move_spread),
        steam_min_move_total=float(settings.steam_min_move_total),
        steam_cooldown_seconds=max(1, int(settings.steam_cooldown_seconds)),
        steam_max_signals_per_event=max(1, int(settings.steam_max_signals_per_event)),
    )


def _timestamp_warning(usage_counts: dict[str, int]) -> str:
    total = sum(int(value) for value in usage_counts.values())
    if total == 0:
        return "No snapshots were processed; timestamp ordering field usage is empty."
    if usage_counts.get("fetched_at", 0) == total:
        return "All snapshots were ordered using fetched_at."

    fallback_parts = [
        f"{field_name}={count}"
        for field_name, count in usage_counts.items()
        if field_name != "fetched_at" and count > 0
    ]
    if not fallback_parts:
        return "Timestamp ordering used fetched_at for all available snapshots."
    return "Fallback ordering fields used: " + ", ".join(fallback_parts)


def _signal_to_csv_row(signal: SimulatedSignal) -> dict[str, object]:
    return {
        "event_id": signal.event_id,
        "signal_type": signal.signal_type,
        "market": signal.market,
        "outcome_name": signal.outcome_name,
        "created_at": signal.created_at.isoformat(),
        "direction": signal.direction,
        "strength_score": signal.strength_score,
        "entry_line": signal.entry_line,
        "entry_price": signal.entry_price,
        "close_line": signal.close_line,
        "close_price": signal.close_price,
        "clv_line": signal.clv_line,
        "clv_prob": signal.clv_prob,
        "metadata_json": json.dumps(signal.metadata, sort_keys=True, separators=(",", ":")),
    }


def _build_clv_by_type(signals: list[SimulatedSignal]) -> dict[str, dict[str, float | int | None]]:
    by_type: dict[str, list[SimulatedSignal]] = defaultdict(list)
    for signal in signals:
        by_type[signal.signal_type].append(signal)

    summary: dict[str, dict[str, float | int | None]] = {}
    for signal_type in sorted(by_type.keys()):
        eligible = [
            signal
            for signal in by_type[signal_type]
            if signal.clv_line is not None or signal.clv_prob is not None
        ]
        count = len(eligible)
        if count == 0:
            summary[signal_type] = {
                "count": 0,
                "pct_positive": 0.0,
                "avg_clv_line": None,
                "median_clv_line": None,
                "avg_clv_prob": None,
                "median_clv_prob": None,
            }
            continue

        positive_count = sum(
            1
            for signal in eligible
            if (signal.clv_line is not None and signal.clv_line > 0)
            or (signal.clv_prob is not None and signal.clv_prob > 0)
        )
        line_values = [float(signal.clv_line) for signal in eligible if signal.clv_line is not None]
        prob_values = [float(signal.clv_prob) for signal in eligible if signal.clv_prob is not None]

        summary[signal_type] = {
            "count": count,
            "pct_positive": (positive_count / count) * 100.0 if count > 0 else 0.0,
            "avg_clv_line": (sum(line_values) / len(line_values)) if line_values else None,
            "median_clv_line": (float(stats_median(line_values)) if line_values else None),
            "avg_clv_prob": (sum(prob_values) / len(prob_values)) if prob_values else None,
            "median_clv_prob": (float(stats_median(prob_values)) if prob_values else None),
        }

    return summary


def _is_positive_signal(signal: SimulatedSignal) -> bool:
    return (
        (signal.clv_line is not None and signal.clv_line > 0)
        or (signal.clv_prob is not None and signal.clv_prob > 0)
    )


def _normalize_score(value: float | int) -> int:
    return max(0, min(100, int(round(float(value)))))


def _resolve_time_bucket(signal: SimulatedSignal) -> str:
    raw_bucket = getattr(signal, "time_bucket", None)
    if raw_bucket is None:
        raw_bucket = signal.metadata.get("time_bucket")
    if not isinstance(raw_bucket, str):
        return "UNKNOWN"
    normalized = raw_bucket.strip().upper()
    if normalized in TIME_BUCKET_ORDER:
        return normalized
    return "UNKNOWN"


def _resolve_segment_score(signal: SimulatedSignal) -> tuple[int, str]:
    composite_value = getattr(signal, "composite_score", None)
    if composite_value is None:
        composite_value = signal.metadata.get("composite_score")
    if isinstance(composite_value, (int, float)) and not isinstance(composite_value, bool):
        return _normalize_score(composite_value), "composite"
    return _normalize_score(signal.strength_score), "strength_fallback"


def _score_band(score: int) -> str:
    if score <= 54:
        return "0-54"
    if score <= 74:
        return "55-74"
    return "75-100"


def _build_segments_time_bucket(signals: list[SimulatedSignal]) -> list[dict[str, object]]:
    aggregates: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"count": 0, "positive_count": 0})
    for signal in signals:
        bucket = _resolve_time_bucket(signal)
        _score, score_source = _resolve_segment_score(signal)
        key = (bucket, score_source)
        aggregates[key]["count"] += 1
        if _is_positive_signal(signal):
            aggregates[key]["positive_count"] += 1

    rows: list[dict[str, object]] = []
    for bucket in TIME_BUCKET_ORDER:
        for score_source in SCORE_SOURCE_ORDER:
            stats = aggregates.get((bucket, score_source))
            if not stats:
                continue
            count = int(stats["count"])
            positive_count = int(stats["positive_count"])
            rows.append(
                {
                    "time_bucket": bucket,
                    "score_source": score_source,
                    "count": count,
                    "positive_count": positive_count,
                    "positive_rate": (positive_count / count) if count > 0 else 0.0,
                }
            )
    return rows


def _build_segments_score_band(signals: list[SimulatedSignal]) -> list[dict[str, object]]:
    aggregates: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"count": 0, "positive_count": 0})
    for signal in signals:
        score, score_source = _resolve_segment_score(signal)
        band = _score_band(score)
        key = (band, score_source)
        aggregates[key]["count"] += 1
        if _is_positive_signal(signal):
            aggregates[key]["positive_count"] += 1

    rows: list[dict[str, object]] = []
    for band in SCORE_BAND_ORDER:
        for score_source in SCORE_SOURCE_ORDER:
            stats = aggregates.get((band, score_source))
            if not stats:
                continue
            count = int(stats["count"])
            positive_count = int(stats["positive_count"])
            rows.append(
                {
                    "score_band": band,
                    "score_source": score_source,
                    "count": count,
                    "positive_count": positive_count,
                    "positive_rate": (positive_count / count) if count > 0 else 0.0,
                }
            )
    return rows


def _family(signal_type: str) -> str | None:
    if signal_type == "STEAM":
        return "STEAM"
    if signal_type == "MULTIBOOK_SYNC":
        return "MULTIBOOK_SYNC"
    if signal_type in {"MOVE", "KEY_CROSS"}:
        return "MOVE_FAMILY"
    return None


def _has_time_within(sorted_target_times: list[datetime], source_time: datetime, window: timedelta) -> bool:
    left = source_time - window
    right = source_time + window
    idx = bisect.bisect_left(sorted_target_times, left)
    if idx >= len(sorted_target_times):
        return False
    return sorted_target_times[idx] <= right


def _build_overlap_directional(signals: list[SimulatedSignal]) -> list[dict[str, float | int | str]]:
    families = ("STEAM", "MULTIBOOK_SYNC", "MOVE_FAMILY")
    grouped: dict[tuple[str, str, str], dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
    for signal in signals:
        family = _family(signal.signal_type)
        if family is None:
            continue
        key = (signal.event_id, signal.market, signal.outcome_name)
        grouped[key][family].append(signal.created_at)

    for family_map in grouped.values():
        for family in families:
            family_map[family].sort()

    window = timedelta(minutes=5)
    rows: list[dict[str, float | int | str]] = []
    for source in families:
        for target in families:
            if source == target:
                continue
            source_count = 0
            matched_count = 0
            for family_map in grouped.values():
                source_times = family_map[source]
                target_times = family_map[target]
                source_count += len(source_times)
                if not source_times or not target_times:
                    continue
                for source_time in source_times:
                    if _has_time_within(target_times, source_time, window):
                        matched_count += 1

            overlap_rate = (matched_count / source_count) if source_count > 0 else 0.0
            rows.append(
                {
                    "source_type": source,
                    "target_type": target,
                    "source_count": source_count,
                    "matched_count": matched_count,
                    "overlap_rate": overlap_rate,
                }
            )

    return rows


def _leaderboard(
    signals: list[SimulatedSignal],
    *,
    metric: str,
    reverse: bool,
    limit: int = 10,
) -> list[dict[str, object]]:
    def _line_sort_key(signal: SimulatedSignal) -> tuple[float, datetime, str, str, str, str]:
        return (
            float(signal.clv_line),
            signal.created_at,
            signal.event_id,
            signal.signal_type,
            signal.market,
            signal.outcome_name,
        )

    def _prob_sort_key(signal: SimulatedSignal) -> tuple[float, datetime, str, str, str, str]:
        return (
            float(signal.clv_prob),
            signal.created_at,
            signal.event_id,
            signal.signal_type,
            signal.market,
            signal.outcome_name,
        )

    if metric == "clv_line":
        candidates = [signal for signal in signals if signal.clv_line is not None]
        sort_key = _line_sort_key
    else:
        candidates = [signal for signal in signals if signal.clv_prob is not None]
        sort_key = _prob_sort_key

    ranked = sorted(candidates, key=sort_key, reverse=reverse)[:limit]
    rows: list[dict[str, object]] = []
    for signal in ranked:
        rows.append(
            {
                "event_id": signal.event_id,
                "signal_type": signal.signal_type,
                "market": signal.market,
                "outcome_name": signal.outcome_name,
                "created_at": signal.created_at.isoformat(),
                "strength_score": signal.strength_score,
                "clv_line": signal.clv_line,
                "clv_prob": signal.clv_prob,
            }
        )
    return rows


async def run_backtest(
    *,
    db: AsyncSession,
    start: datetime,
    end: datetime,
    sport_key: str,
    step_seconds: int,
    markets: tuple[str, ...],
    lookback_minutes: int,
    min_books: int,
) -> tuple[list[SimulatedSignal], dict]:
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if end_utc <= start_utc:
        raise ValueError("--end must be greater than --start")

    games_stmt = (
        select(Game)
        .where(
            Game.sport_key == sport_key,
            Game.commence_time >= start_utc,
            Game.commence_time < end_utc,
        )
        .order_by(Game.commence_time.asc(), Game.event_id.asc())
    )
    games = (await db.execute(games_stmt)).scalars().all()
    if not games:
        summary = {
            "run_args": {
                "start": start_utc.isoformat(),
                "end": end_utc.isoformat(),
                "sport_key": sport_key,
                "step_seconds": step_seconds,
                "markets": list(markets),
                "lookback_minutes": lookback_minutes,
                "min_books": min_books,
            },
            "timestamp_field_used_counts": {},
            "timestamp_ordering_warning": _timestamp_warning({}),
            "games_processed": 0,
            "signals_total": 0,
            "signals_by_type": {},
            "clv_by_type": {},
            "overlap_directional_5m": [],
            "top_clv_line": [],
            "bottom_clv_line": [],
            "top_clv_prob": [],
            "bottom_clv_prob": [],
            "segments_time_bucket": [],
            "segments_score_band": [],
        }
        return [], summary

    event_ids = [game.event_id for game in games]
    snapshots_stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id.in_(event_ids),
            OddsSnapshot.market.in_(markets),
        )
        .order_by(OddsSnapshot.event_id.asc(), OddsSnapshot.id.asc())
    )
    snapshots = (await db.execute(snapshots_stmt)).scalars().all()

    snapshots_by_event: dict[str, list[OddsSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_event[snapshot.event_id].append(snapshot)

    rule_config = _build_rule_config(
        markets=markets,
        lookback_minutes=lookback_minutes,
        min_books=min_books,
    )
    timestamp_field_usage: Counter[str] = Counter()
    all_signals: list[SimulatedSignal] = []
    step_delta = timedelta(seconds=max(1, step_seconds))

    for game in games:
        game_snapshots = snapshots_by_event.get(game.event_id, [])
        event_data = build_event_replay_data(
            event_id=game.event_id,
            commence_time=game.commence_time,
            snapshots=game_snapshots,
            markets=markets,
            timestamp_field_usage=timestamp_field_usage,
        )
        if not event_data.sorted_snapshots:
            continue

        event_signals: list[SimulatedSignal] = []
        cooldown_cache: dict[str, datetime] = {}
        timeline_start = event_data.sorted_snapshots[0].effective_timestamp
        timeline_end = event_data.commence_time

        timeline: list[datetime] = []
        cursor = timeline_start
        while cursor <= timeline_end:
            timeline.append(cursor)
            cursor = cursor + step_delta
        if not timeline or timeline[-1] < timeline_end:
            timeline.append(timeline_end)

        for now in timeline:
            consensus_map = compute_consensus_at_t(event_data, now, rule_config)
            event_signals.extend(detect_move_at_t(event_data, now, rule_config, cooldown_cache))
            event_signals.extend(detect_multibook_sync_at_t(event_data, now, rule_config, cooldown_cache))
            event_signals.extend(
                detect_dislocation_at_t(
                    event_data,
                    now,
                    rule_config,
                    cooldown_cache,
                    consensus_map=consensus_map,
                )
            )
            event_signals.extend(detect_steam_at_t(event_data, now, rule_config, cooldown_cache))

        close_consensus = compute_consensus_at_t(event_data, event_data.commence_time, rule_config)
        apply_pseudo_clv(event_signals, close_consensus)
        all_signals.extend(event_signals)

    all_signals = sort_simulated_signals(all_signals)

    signals_by_type: dict[str, int] = {}
    for signal in all_signals:
        signals_by_type[signal.signal_type] = signals_by_type.get(signal.signal_type, 0) + 1
    signals_by_type = dict(sorted(signals_by_type.items(), key=lambda item: item[0]))

    timestamp_field_used_counts = {
        key: int(value)
        for key, value in sorted(timestamp_field_usage.items(), key=lambda item: item[0])
    }

    summary = {
        "run_args": {
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
            "sport_key": sport_key,
            "step_seconds": step_seconds,
            "markets": list(markets),
            "lookback_minutes": lookback_minutes,
            "min_books": min_books,
        },
        "timestamp_field_used_counts": timestamp_field_used_counts,
        "timestamp_ordering_warning": _timestamp_warning(timestamp_field_used_counts),
        "games_processed": len(games),
        "signals_total": len(all_signals),
        "signals_by_type": signals_by_type,
        "clv_by_type": _build_clv_by_type(all_signals),
        "overlap_directional_5m": _build_overlap_directional(all_signals),
        "top_clv_line": _leaderboard(all_signals, metric="clv_line", reverse=True),
        "bottom_clv_line": _leaderboard(all_signals, metric="clv_line", reverse=False),
        "top_clv_prob": _leaderboard(all_signals, metric="clv_prob", reverse=True),
        "bottom_clv_prob": _leaderboard(all_signals, metric="clv_prob", reverse=False),
        "segments_time_bucket": _build_segments_time_bucket(all_signals),
        "segments_score_band": _build_segments_score_band(all_signals),
    }
    return all_signals, summary


def _write_reports(
    *,
    signals: list[SimulatedSignal],
    summary: dict,
    output_dir: Path,
    start: datetime,
    end: datetime,
) -> Path:
    run_utc = datetime.now(UTC)
    run_dir = output_dir / (
        f"backtest_{start.date().isoformat()}_{end.date().isoformat()}_{run_utc.strftime('%Y%m%dT%H%M%SZ')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    csv_path = run_dir / "backtest_signals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "event_id",
            "signal_type",
            "market",
            "outcome_name",
            "created_at",
            "direction",
            "strength_score",
            "entry_line",
            "entry_price",
            "close_line",
            "close_price",
            "clv_line",
            "clv_prob",
            "metadata_json",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for signal in signals:
            writer.writerow(_signal_to_csv_row(signal))

    summary_path = run_dir / "backtest_summary.json"
    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2, sort_keys=True)

    return run_dir


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline odds snapshot backtest replay")
    parser.add_argument("--start", required=True, help="UTC start date inclusive (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="UTC end date exclusive (YYYY-MM-DD)")
    parser.add_argument("--sport_key", default="basketball_nba", help="Sport key filter")
    parser.add_argument("--step_seconds", type=int, default=60, help="Replay step size in seconds")
    parser.add_argument(
        "--markets",
        default="spreads,totals,h2h",
        help="Comma-separated markets (spreads,totals,h2h)",
    )
    parser.add_argument("--lookback_minutes", type=int, default=10, help="Consensus lookback window")
    parser.add_argument("--min_books", type=int, default=5, help="Minimum books for consensus/dislocation")
    parser.add_argument(
        "--output_dir",
        default=str(_default_output_dir()),
        help="Output directory for reports",
    )
    return parser


async def _async_main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    start = _parse_utc_date(args.start)
    end = _parse_utc_date(args.end)
    markets = _parse_markets(args.markets)
    output_dir = Path(args.output_dir).resolve()

    async with AsyncSessionLocal() as db:
        signals, summary = await run_backtest(
            db=db,
            start=start,
            end=end,
            sport_key=str(args.sport_key),
            step_seconds=max(1, int(args.step_seconds)),
            markets=markets,
            lookback_minutes=max(1, int(args.lookback_minutes)),
            min_books=max(1, int(args.min_books)),
        )

    run_dir = _write_reports(
        signals=signals,
        summary=summary,
        output_dir=output_dir,
        start=start,
        end=end,
    )

    print(f"Backtest completed. Reports written to: {run_dir}")
    print(f"Signals generated: {len(signals)}")
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
