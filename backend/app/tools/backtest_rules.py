from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean, median as stats_median, pstdev
from typing import Any

from app.services.signals import (
    american_to_implied_prob,
    compute_strength_dislocation,
    compute_strength_score,
    compute_strength_steam,
    should_trigger_spread_move,
    should_trigger_total_move,
)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(stats_median(values))


def _pstdev(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return float(pstdev(values))


def _direction(from_value: float, to_value: float) -> str:
    if to_value > from_value:
        return "UP"
    if to_value < from_value:
        return "DOWN"
    return "FLAT"


def resolve_snapshot_ordering(snapshot: Any) -> tuple[datetime | None, str, str]:
    """Resolve snapshot ordering by timestamp fallback: fetched -> created -> updated -> PK."""
    for field_name in ("fetched_at", "created_at", "updated_at"):
        value = getattr(snapshot, field_name, None)
        if isinstance(value, datetime):
            return _ensure_utc(value), field_name, str(getattr(snapshot, "id", ""))
    return None, "primary_key", str(getattr(snapshot, "id", ""))


def snapshot_ordering_tuple(snapshot: Any, fallback_timestamp: datetime) -> tuple[datetime, str]:
    """Deterministic sort tuple for snapshots based on resolved ordering timestamp + PK."""
    resolved_ts, _field_name, row_id = resolve_snapshot_ordering(snapshot)
    return (resolved_ts or _ensure_utc(fallback_timestamp), row_id)


@dataclass(frozen=True)
class BacktestRuleConfig:
    markets: tuple[str, ...]
    lookback_minutes: int
    min_books: int
    nba_key_numbers: tuple[float, ...]
    dislocation_spread_line_delta: float
    dislocation_total_line_delta: float
    dislocation_ml_implied_prob_delta: float
    dislocation_cooldown_seconds: int
    dislocation_max_signals_per_event: int
    steam_window_minutes: int
    steam_min_books: int
    steam_min_move_spread: float
    steam_min_move_total: float
    steam_cooldown_seconds: int
    steam_max_signals_per_event: int


@dataclass(frozen=True)
class PreparedSnapshot:
    event_id: str
    market: str
    outcome_name: str
    sportsbook_key: str
    line: float | None
    price: int
    order_timestamp: datetime | None
    order_field: str
    row_id: str
    effective_timestamp: datetime


@dataclass(frozen=True)
class ConsensusPoint:
    event_id: str
    market: str
    outcome_name: str
    consensus_line: float | None
    consensus_price: float | None
    dispersion: float | None
    books_count: int


@dataclass
class SimulatedSignal:
    event_id: str
    signal_type: str
    market: str
    outcome_name: str
    created_at: datetime
    direction: str
    strength_score: int
    entry_line: float | None
    entry_price: float | None
    from_value: float | None
    to_value: float | None
    from_price: float | None
    to_price: float | None
    window_minutes: int
    books_affected: int
    velocity_minutes: float
    metadata: dict[str, Any]
    close_line: float | None = None
    close_price: float | None = None
    clv_line: float | None = None
    clv_prob: float | None = None


@dataclass
class EventReplayData:
    event_id: str
    commence_time: datetime
    window_start: datetime
    sorted_snapshots: list[PreparedSnapshot]
    by_key: dict[tuple[str, str, str], list[PreparedSnapshot]]
    times_by_key: dict[tuple[str, str, str], list[datetime]]
    by_group: dict[tuple[str, str], list[PreparedSnapshot]]
    times_by_group: dict[tuple[str, str], list[datetime]]
    outcomes_by_market: dict[str, set[str]]


@dataclass(frozen=True)
class _DislocationCandidate:
    signal: SimulatedSignal
    dedupe_key: str
    delta_abs: float
    strength_score: int


@dataclass(frozen=True)
class _SteamCandidate:
    signal: SimulatedSignal
    dedupe_key: str
    total_move_abs: float
    strength_score: int


def build_event_replay_data(
    *,
    event_id: str,
    commence_time: datetime,
    snapshots: list[Any],
    markets: tuple[str, ...],
    timestamp_field_usage: Counter[str] | None = None,
) -> EventReplayData:
    commence_utc = _ensure_utc(commence_time)
    window_start = commence_utc - timedelta(hours=24)
    market_set = set(markets)

    prepared: list[PreparedSnapshot] = []
    for snapshot in snapshots:
        ts, field_used, row_id = resolve_snapshot_ordering(snapshot)
        if timestamp_field_usage is not None:
            timestamp_field_usage[field_used] += 1

        snapshot_event_id = str(getattr(snapshot, "event_id", "")).strip()
        if snapshot_event_id != event_id:
            continue

        market = str(getattr(snapshot, "market", "")).strip()
        if market not in market_set:
            continue

        outcome_name = str(getattr(snapshot, "outcome_name", "")).strip()
        sportsbook_key = str(getattr(snapshot, "sportsbook_key", "")).strip()
        if not outcome_name or not sportsbook_key:
            continue

        price_raw = getattr(snapshot, "price", None)
        try:
            price = int(price_raw)
        except (TypeError, ValueError):
            continue

        line_raw = getattr(snapshot, "line", None)
        line: float | None = None
        if line_raw is not None:
            try:
                line = float(line_raw)
            except (TypeError, ValueError):
                line = None

        if ts is not None and (ts < window_start or ts > commence_utc):
            continue
        effective_timestamp = ts if ts is not None else window_start

        prepared.append(
            PreparedSnapshot(
                event_id=event_id,
                market=market,
                outcome_name=outcome_name,
                sportsbook_key=sportsbook_key,
                line=line,
                price=price,
                order_timestamp=ts,
                order_field=field_used,
                row_id=row_id,
                effective_timestamp=effective_timestamp,
            )
        )

    prepared.sort(key=lambda row: (row.effective_timestamp, row.row_id))

    by_key: dict[tuple[str, str, str], list[PreparedSnapshot]] = defaultdict(list)
    by_group: dict[tuple[str, str], list[PreparedSnapshot]] = defaultdict(list)
    outcomes_by_market: dict[str, set[str]] = defaultdict(set)
    for row in prepared:
        by_key[(row.market, row.outcome_name, row.sportsbook_key)].append(row)
        by_group[(row.market, row.outcome_name)].append(row)
        outcomes_by_market[row.market].add(row.outcome_name)

    times_by_key = {
        key: [row.effective_timestamp for row in rows]
        for key, rows in by_key.items()
    }
    times_by_group = {
        key: [row.effective_timestamp for row in rows]
        for key, rows in by_group.items()
    }

    return EventReplayData(
        event_id=event_id,
        commence_time=commence_utc,
        window_start=window_start,
        sorted_snapshots=prepared,
        by_key=dict(by_key),
        times_by_key=times_by_key,
        by_group=dict(by_group),
        times_by_group=times_by_group,
        outcomes_by_market=dict(outcomes_by_market),
    )


def _window_slice(
    rows: list[PreparedSnapshot],
    timestamps: list[datetime],
    start_ts: datetime,
    end_ts: datetime,
) -> list[PreparedSnapshot]:
    left = bisect.bisect_left(timestamps, start_ts)
    right = bisect.bisect_right(timestamps, end_ts)
    return rows[left:right]


def _latest_snapshot_by_key_in_window(
    event_data: EventReplayData,
    *,
    now: datetime,
    lookback_minutes: int,
    markets: tuple[str, ...],
) -> dict[tuple[str, str, str], PreparedSnapshot]:
    now_utc = _ensure_utc(now)
    cutoff = now_utc - timedelta(minutes=max(1, lookback_minutes))
    market_set = set(markets)
    latest: dict[tuple[str, str, str], PreparedSnapshot] = {}

    for key in sorted(event_data.by_key.keys()):
        market, _outcome_name, _sportsbook = key
        if market not in market_set:
            continue
        rows = event_data.by_key[key]
        times = event_data.times_by_key[key]
        idx = bisect.bisect_right(times, now_utc) - 1
        if idx < 0:
            continue
        candidate = rows[idx]
        if candidate.effective_timestamp < cutoff:
            continue
        latest[key] = candidate

    return latest


def compute_consensus_at_t(
    event_data: EventReplayData,
    now: datetime,
    config: BacktestRuleConfig,
) -> dict[tuple[str, str], ConsensusPoint]:
    latest = _latest_snapshot_by_key_in_window(
        event_data,
        now=now,
        lookback_minutes=config.lookback_minutes,
        markets=config.markets,
    )
    if not latest:
        return {}

    grouped: dict[tuple[str, str], list[PreparedSnapshot]] = defaultdict(list)
    for (market, outcome_name, _sportsbook_key), snapshot in latest.items():
        grouped[(market, outcome_name)].append(snapshot)

    consensus_map: dict[tuple[str, str], ConsensusPoint] = {}
    for market, outcome_name in sorted(grouped.keys()):
        snapshots = grouped[(market, outcome_name)]
        books_count = len({snap.sportsbook_key for snap in snapshots})
        if books_count < config.min_books:
            continue

        prices = [float(snap.price) for snap in snapshots]
        lines = [float(snap.line) for snap in snapshots if snap.line is not None]

        if market == "h2h":
            probs = [american_to_implied_prob(price) for price in prices]
            prob_values = [float(prob) for prob in probs if prob is not None]
            consensus_line = None
            consensus_price = _median(prices)
            dispersion = _pstdev(prob_values)
        else:
            consensus_line = _median(lines)
            consensus_price = _median(prices) if prices else None
            dispersion = _pstdev(lines)

        consensus_map[(market, outcome_name)] = ConsensusPoint(
            event_id=event_data.event_id,
            market=market,
            outcome_name=outcome_name,
            consensus_line=consensus_line,
            consensus_price=consensus_price,
            dispersion=dispersion,
            books_count=books_count,
        )

    return consensus_map


def _cooldown_allows(
    cooldown_cache: dict[str, datetime],
    *,
    key: str,
    now: datetime,
    cooldown_seconds: int,
) -> bool:
    now_utc = _ensure_utc(now)
    expires_at = cooldown_cache.get(key)
    if expires_at is not None and expires_at > now_utc:
        return False
    cooldown_cache[key] = now_utc + timedelta(seconds=max(1, cooldown_seconds))
    return True


def detect_move_at_t(
    event_data: EventReplayData,
    now: datetime,
    config: BacktestRuleConfig,
    cooldown_cache: dict[str, datetime],
) -> list[SimulatedSignal]:
    now_utc = _ensure_utc(now)
    created: list[SimulatedSignal] = []

    for market, window_minutes in (("spreads", 10), ("totals", 15)):
        if market not in config.markets:
            continue

        cutoff = now_utc - timedelta(minutes=window_minutes)
        for outcome_name in sorted(event_data.outcomes_by_market.get(market, set())):
            key = (market, outcome_name)
            rows = event_data.by_group.get(key, [])
            if not rows:
                continue
            times = event_data.times_by_group[key]
            window_rows = _window_slice(rows, times, cutoff, now_utc)
            line_rows = [row for row in window_rows if row.line is not None]
            if len(line_rows) < 2:
                continue

            from_snapshot = line_rows[0]
            to_snapshot = line_rows[-1]
            from_value = float(from_snapshot.line)  # line is guaranteed by filter
            to_value = float(to_snapshot.line)

            direction = _direction(from_value, to_value)
            if direction == "FLAT":
                continue

            if market == "spreads":
                triggered, signal_type, key_cross, magnitude = should_trigger_spread_move(
                    from_value,
                    to_value,
                    config.nba_key_numbers,
                )
            else:
                triggered, magnitude = should_trigger_total_move(from_value, to_value)
                signal_type = "MOVE"
                key_cross = False

            if not triggered:
                continue

            dedupe_key = (
                f"signal:{event_data.event_id}:{market}:{signal_type}:{direction}:"
                f"{outcome_name}:{round(from_value, 2)}:{round(to_value, 2)}"
            )
            if not _cooldown_allows(
                cooldown_cache,
                key=dedupe_key,
                now=now_utc,
                cooldown_seconds=window_minutes * 60,
            ):
                continue

            velocity_minutes = max(
                0.1,
                (to_snapshot.effective_timestamp - from_snapshot.effective_timestamp).total_seconds() / 60.0,
            )
            books = sorted({snap.sportsbook_key for snap in line_rows})
            minutes_to_tip = (event_data.commence_time - now_utc).total_seconds() / 60.0
            strength_score, components = compute_strength_score(
                magnitude=magnitude,
                velocity_minutes=velocity_minutes,
                window_minutes=window_minutes,
                books_affected=len(books),
                minutes_to_tip=minutes_to_tip,
            )

            created.append(
                SimulatedSignal(
                    event_id=event_data.event_id,
                    signal_type=signal_type,
                    market=market,
                    outcome_name=outcome_name,
                    created_at=now_utc,
                    direction=direction,
                    strength_score=strength_score,
                    entry_line=to_value,
                    entry_price=float(to_snapshot.price),
                    from_value=from_value,
                    to_value=to_value,
                    from_price=float(from_snapshot.price),
                    to_price=float(to_snapshot.price),
                    window_minutes=window_minutes,
                    books_affected=len(books),
                    velocity_minutes=velocity_minutes,
                    metadata={
                        "outcome_name": outcome_name,
                        "magnitude": round(float(magnitude), 6),
                        "key_cross": bool(key_cross),
                        "books": books,
                        "minutes_to_tip": round(minutes_to_tip, 2),
                        "components": components,
                    },
                )
            )

    return created


def detect_multibook_sync_at_t(
    event_data: EventReplayData,
    now: datetime,
    config: BacktestRuleConfig,
    cooldown_cache: dict[str, datetime],
) -> list[SimulatedSignal]:
    window_minutes = 5
    now_utc = _ensure_utc(now)
    cutoff = now_utc - timedelta(minutes=window_minutes)

    aggregate: dict[tuple[str, str, str], list[dict[str, float | str]]] = defaultdict(list)
    for market, outcome_name, sportsbook_key in sorted(event_data.by_key.keys()):
        if market not in config.markets:
            continue
        key = (market, outcome_name, sportsbook_key)
        rows = event_data.by_key[key]
        times = event_data.times_by_key[key]
        window_rows = _window_slice(rows, times, cutoff, now_utc)
        if len(window_rows) < 2:
            continue

        from_snapshot = window_rows[0]
        to_snapshot = window_rows[-1]
        from_value = (
            float(from_snapshot.line)
            if from_snapshot.line is not None
            else float(from_snapshot.price)
        )
        to_value = (
            float(to_snapshot.line)
            if to_snapshot.line is not None
            else float(to_snapshot.price)
        )
        if from_value == to_value:
            continue

        direction = _direction(from_value, to_value)
        if direction == "FLAT":
            continue
        velocity_minutes = max(
            0.1,
            (to_snapshot.effective_timestamp - from_snapshot.effective_timestamp).total_seconds() / 60.0,
        )
        aggregate[(market, outcome_name, direction)].append(
            {
                "sportsbook_key": sportsbook_key,
                "from_value": from_value,
                "to_value": to_value,
                "velocity_minutes": velocity_minutes,
            }
        )

    created: list[SimulatedSignal] = []
    for market, outcome_name, direction in sorted(aggregate.keys()):
        moves = aggregate[(market, outcome_name, direction)]
        if len(moves) < 3:
            continue

        avg_from = float(mean([float(move["from_value"]) for move in moves]))
        avg_to = float(mean([float(move["to_value"]) for move in moves]))
        magnitude = abs(avg_to - avg_from)
        velocity = float(mean([float(move["velocity_minutes"]) for move in moves]))

        dedupe_key = (
            f"signal:{event_data.event_id}:{market}:MULTIBOOK_SYNC:{direction}:"
            f"{outcome_name}:{round(avg_to, 2)}:{len(moves)}"
        )
        if not _cooldown_allows(
            cooldown_cache,
            key=dedupe_key,
            now=now_utc,
            cooldown_seconds=window_minutes * 60,
        ):
            continue

        minutes_to_tip = (event_data.commence_time - now_utc).total_seconds() / 60.0
        strength_score, components = compute_strength_score(
            magnitude=magnitude,
            velocity_minutes=velocity,
            window_minutes=window_minutes,
            books_affected=len(moves),
            minutes_to_tip=minutes_to_tip,
        )
        books = sorted(str(move["sportsbook_key"]) for move in moves)

        created.append(
            SimulatedSignal(
                event_id=event_data.event_id,
                signal_type="MULTIBOOK_SYNC",
                market=market,
                outcome_name=outcome_name,
                created_at=now_utc,
                direction=direction,
                strength_score=strength_score,
                entry_line=avg_to if market != "h2h" else None,
                entry_price=float(round(avg_to)) if market == "h2h" else None,
                from_value=avg_from,
                to_value=avg_to,
                from_price=float(round(avg_from)) if market == "h2h" else None,
                to_price=float(round(avg_to)) if market == "h2h" else None,
                window_minutes=window_minutes,
                books_affected=len(moves),
                velocity_minutes=velocity,
                metadata={
                    "outcome_name": outcome_name,
                    "books": books,
                    "magnitude": round(magnitude, 6),
                    "minutes_to_tip": round(minutes_to_tip, 2),
                    "components": components,
                },
            )
        )

    return created


def detect_dislocation_at_t(
    event_data: EventReplayData,
    now: datetime,
    config: BacktestRuleConfig,
    cooldown_cache: dict[str, datetime],
    consensus_map: dict[tuple[str, str], ConsensusPoint] | None = None,
) -> list[SimulatedSignal]:
    now_utc = _ensure_utc(now)
    if consensus_map is None:
        consensus_map = compute_consensus_at_t(event_data, now_utc, config)
    if not consensus_map:
        return []

    latest = _latest_snapshot_by_key_in_window(
        event_data,
        now=now_utc,
        lookback_minutes=config.lookback_minutes,
        markets=config.markets,
    )
    if not latest:
        return []

    by_group: dict[tuple[str, str], list[PreparedSnapshot]] = defaultdict(list)
    for (market, outcome_name, _sportsbook_key), snapshot in latest.items():
        by_group[(market, outcome_name)].append(snapshot)

    candidates: list[_DislocationCandidate] = []
    for market, outcome_name in sorted(consensus_map.keys()):
        consensus = consensus_map[(market, outcome_name)]
        group_snapshots = sorted(
            by_group.get((market, outcome_name), []),
            key=lambda row: row.sportsbook_key,
        )
        for snapshot in group_snapshots:
            delta_type = "line"
            from_value = 0.0
            to_value = 0.0
            from_price: float | None = None
            to_price: float | None = None

            if market in {"spreads", "totals"}:
                if consensus.consensus_line is None or snapshot.line is None:
                    continue
                threshold = (
                    config.dislocation_spread_line_delta
                    if market == "spreads"
                    else config.dislocation_total_line_delta
                )
                from_value = float(consensus.consensus_line)
                to_value = float(snapshot.line)
                delta = to_value - from_value
                if abs(delta) < threshold:
                    continue
                from_price = float(consensus.consensus_price) if consensus.consensus_price is not None else None
                to_price = float(snapshot.price)
            else:
                if consensus.consensus_price is None:
                    continue
                consensus_prob = american_to_implied_prob(consensus.consensus_price)
                book_prob = american_to_implied_prob(snapshot.price)
                if consensus_prob is None or book_prob is None:
                    continue
                delta_type = "implied_prob"
                from_value = float(consensus_prob)
                to_value = float(book_prob)
                delta = to_value - from_value
                if abs(delta) < config.dislocation_ml_implied_prob_delta:
                    continue
                from_price = float(consensus.consensus_price)
                to_price = float(snapshot.price)

            strength_score = compute_strength_dislocation(
                delta=abs(float(delta)),
                dispersion=consensus.dispersion,
                books_count=consensus.books_count,
                market=market,
            )
            direction = _direction(from_value, to_value)
            dedupe_key = (
                f"signal:dislocation:{event_data.event_id}:{market}:"
                f"{outcome_name}:{snapshot.sportsbook_key}"
            )
            signal = SimulatedSignal(
                event_id=event_data.event_id,
                signal_type="DISLOCATION",
                market=market,
                outcome_name=outcome_name,
                created_at=now_utc,
                direction=direction,
                strength_score=strength_score,
                entry_line=float(snapshot.line) if snapshot.line is not None else None,
                entry_price=float(snapshot.price),
                from_value=from_value,
                to_value=to_value,
                from_price=from_price,
                to_price=to_price,
                window_minutes=max(1, config.lookback_minutes),
                books_affected=1,
                velocity_minutes=0.1,
                metadata={
                    "book_key": snapshot.sportsbook_key,
                    "market": market,
                    "outcome_name": outcome_name,
                    "book_line": float(snapshot.line) if snapshot.line is not None else None,
                    "book_price": float(snapshot.price),
                    "consensus_line": (
                        float(consensus.consensus_line) if consensus.consensus_line is not None else None
                    ),
                    "consensus_price": (
                        float(consensus.consensus_price) if consensus.consensus_price is not None else None
                    ),
                    "dispersion": float(consensus.dispersion) if consensus.dispersion is not None else None,
                    "books_count": int(consensus.books_count),
                    "delta": round(float(delta), 6),
                    "delta_type": delta_type,
                    "lookback_minutes": max(1, config.lookback_minutes),
                },
            )
            candidates.append(
                _DislocationCandidate(
                    signal=signal,
                    dedupe_key=dedupe_key,
                    delta_abs=abs(float(delta)),
                    strength_score=strength_score,
                )
            )

    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.strength_score,
            candidate.delta_abs,
            candidate.signal.market,
            candidate.signal.outcome_name,
            candidate.signal.metadata.get("book_key", ""),
        ),
        reverse=True,
    )

    created: list[SimulatedSignal] = []
    for candidate in ranked[: max(1, config.dislocation_max_signals_per_event)]:
        if not _cooldown_allows(
            cooldown_cache,
            key=candidate.dedupe_key,
            now=now_utc,
            cooldown_seconds=max(1, config.dislocation_cooldown_seconds),
        ):
            continue
        created.append(candidate.signal)

    return created


def _steam_market_threshold(market: str, config: BacktestRuleConfig) -> float:
    if market == "spreads":
        return max(0.0, float(config.steam_min_move_spread))
    if market == "totals":
        return max(0.0, float(config.steam_min_move_total))
    return 0.0


def _steam_min_per_book_move(market: str, config: BacktestRuleConfig) -> float:
    return max(0.05, _steam_market_threshold(market, config) * 0.4)


def detect_steam_at_t(
    event_data: EventReplayData,
    now: datetime,
    config: BacktestRuleConfig,
    cooldown_cache: dict[str, datetime],
) -> list[SimulatedSignal]:
    now_utc = _ensure_utc(now)
    window_minutes = max(1, config.steam_window_minutes)
    cutoff = now_utc - timedelta(minutes=window_minutes)
    eligible_markets = {
        market
        for market in config.markets
        if market in {"spreads", "totals"}
    }
    if not eligible_markets:
        return []

    grouped: dict[tuple[str, str, str], list[dict[str, float | str]]] = defaultdict(list)
    for market, outcome_name, sportsbook_key in sorted(event_data.by_key.keys()):
        if market not in eligible_markets:
            continue
        key = (market, outcome_name, sportsbook_key)
        rows = event_data.by_key[key]
        times = event_data.times_by_key[key]
        window_rows = _window_slice(rows, times, cutoff, now_utc)
        if len(window_rows) < 2:
            continue

        earliest = window_rows[0]
        latest = window_rows[-1]
        if earliest.line is None or latest.line is None:
            continue
        earliest_line = float(earliest.line)
        latest_line = float(latest.line)
        move = latest_line - earliest_line
        if abs(move) < _steam_min_per_book_move(market, config):
            continue

        direction = _direction(earliest_line, latest_line)
        if direction not in {"UP", "DOWN"}:
            continue

        grouped[(market, outcome_name, direction)].append(
            {
                "sportsbook_key": sportsbook_key,
                "earliest_line": earliest_line,
                "latest_line": latest_line,
                "move": move,
            }
        )

    candidates: list[_SteamCandidate] = []
    for market, outcome_name, direction in sorted(grouped.keys()):
        moves = grouped[(market, outcome_name, direction)]
        if len(moves) < max(1, config.steam_min_books):
            continue

        start_line = float(stats_median([float(move["earliest_line"]) for move in moves]))
        end_line = float(stats_median([float(move["latest_line"]) for move in moves]))
        total_move = end_line - start_line
        threshold = _steam_market_threshold(market, config)
        if abs(total_move) < threshold:
            continue

        avg_move = float(mean([float(move["move"]) for move in moves]))
        speed = abs(total_move) / float(window_minutes)
        books_involved = sorted(str(move["sportsbook_key"]) for move in moves)
        direction_lower = "up" if direction == "UP" else "down"
        strength_score = compute_strength_steam(
            total_move=total_move,
            speed=speed,
            books_count=len(books_involved),
            market=market,
        )
        dedupe_key = f"signal:steam:{event_data.event_id}:{market}:{outcome_name}:{direction_lower}"
        signal = SimulatedSignal(
            event_id=event_data.event_id,
            signal_type="STEAM",
            market=market,
            outcome_name=outcome_name,
            created_at=now_utc,
            direction=direction,
            strength_score=strength_score,
            entry_line=end_line,
            entry_price=None,
            from_value=start_line,
            to_value=end_line,
            from_price=None,
            to_price=None,
            window_minutes=window_minutes,
            books_affected=len(books_involved),
            velocity_minutes=float(window_minutes),
            metadata={
                "market": market,
                "outcome_name": outcome_name,
                "direction": direction_lower,
                "books_involved": books_involved,
                "window_minutes": window_minutes,
                "total_move": round(total_move, 6),
                "avg_move": round(avg_move, 6),
                "start_line": round(start_line, 6),
                "end_line": round(end_line, 6),
                "entry_line": round(end_line, 6),
                "speed": round(speed, 6),
            },
        )
        candidates.append(
            _SteamCandidate(
                signal=signal,
                dedupe_key=dedupe_key,
                total_move_abs=abs(total_move),
                strength_score=strength_score,
            )
        )

    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.strength_score,
            candidate.total_move_abs,
            candidate.signal.books_affected,
            candidate.signal.market,
            candidate.signal.outcome_name,
        ),
        reverse=True,
    )

    created: list[SimulatedSignal] = []
    for candidate in ranked[: max(1, config.steam_max_signals_per_event)]:
        if not _cooldown_allows(
            cooldown_cache,
            key=candidate.dedupe_key,
            now=now_utc,
            cooldown_seconds=max(1, config.steam_cooldown_seconds),
        ):
            continue
        created.append(candidate.signal)

    return created


def apply_pseudo_clv(
    signals: list[SimulatedSignal],
    close_consensus: dict[tuple[str, str], ConsensusPoint],
) -> None:
    for signal in signals:
        close = close_consensus.get((signal.market, signal.outcome_name))
        if close is None:
            continue

        signal.close_line = close.consensus_line
        signal.close_price = close.consensus_price

        if signal.entry_line is not None and signal.close_line is not None:
            signal.clv_line = float(signal.close_line) - float(signal.entry_line)

        close_prob = american_to_implied_prob(signal.close_price)
        entry_prob = american_to_implied_prob(signal.entry_price)
        if close_prob is not None and entry_prob is not None:
            signal.clv_prob = float(close_prob) - float(entry_prob)


def sort_simulated_signals(signals: list[SimulatedSignal]) -> list[SimulatedSignal]:
    return sorted(
        signals,
        key=lambda signal: (
            _ensure_utc(signal.created_at),
            signal.event_id,
            signal.signal_type,
            signal.market,
            signal.outcome_name,
            signal.direction,
            signal.metadata.get("book_key", ""),
        ),
    )
