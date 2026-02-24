import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.tools.backtest import (
    SCORE_BAND_ORDER,
    SCORE_SOURCE_ORDER,
    TIME_BUCKET_ORDER,
    _build_segments_score_band,
    _build_segments_time_bucket,
)
from app.tools.backtest import run_backtest
from app.tools.backtest_rules import SimulatedSignal, resolve_snapshot_ordering, snapshot_ordering_tuple


def _snapshot(
    *,
    event_id: str,
    sportsbook_key: str,
    market: str,
    outcome_name: str,
    line: float | None,
    price: int,
    fetched_at: datetime,
    commence_time: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="NYK",
        away_team="BOS",
        sportsbook_key=sportsbook_key,
        market=market,
        outcome_name=outcome_name,
        line=line,
        price=price,
        fetched_at=fetched_at,
    )


def _signal_fingerprint(signals: list) -> list[tuple]:
    return [
        (
            signal.event_id,
            signal.signal_type,
            signal.market,
            signal.outcome_name,
            signal.created_at.isoformat(),
            signal.direction,
            signal.strength_score,
            signal.entry_line,
            signal.entry_price,
            signal.close_line,
            signal.close_price,
            signal.clv_line,
            signal.clv_prob,
            json.dumps(signal.metadata, sort_keys=True, separators=(",", ":")),
        )
        for signal in signals
    ]


async def test_backtest_replay_is_deterministic(db_session: AsyncSession) -> None:
    commence_time = datetime(2026, 1, 10, 1, 0, tzinfo=UTC)
    event_id = "event_backtest_deterministic"
    game = Game(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team="NYK",
        away_team="BOS",
    )
    db_session.add(game)

    books = ["book1", "book2", "book3", "book4", "book5"]
    rows: list[OddsSnapshot] = []

    for idx, book in enumerate(books):
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=-3.0 - (0.05 * idx),
                price=-110,
                fetched_at=commence_time - timedelta(minutes=25),
                commence_time=commence_time,
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="spreads",
                outcome_name="BOS",
                line=-3.8 - (0.05 * idx),
                price=-108,
                fetched_at=commence_time - timedelta(minutes=13),
                commence_time=commence_time,
            )
        )

    rows.append(
        _snapshot(
            event_id=event_id,
            sportsbook_key="book5",
            market="spreads",
            outcome_name="BOS",
            line=-5.3,
            price=-110,
            fetched_at=commence_time - timedelta(minutes=11),
            commence_time=commence_time,
        )
    )

    for idx, book in enumerate(books):
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=224.0 + (0.1 * idx),
                price=-110,
                fetched_at=commence_time - timedelta(minutes=4),
                commence_time=commence_time,
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="totals",
                outcome_name="Over",
                line=225.2 + (0.1 * idx),
                price=-109,
                fetched_at=commence_time - timedelta(minutes=2),
                commence_time=commence_time,
            )
        )

    for idx, book in enumerate(books):
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="h2h",
                outcome_name="BOS",
                line=None,
                price=120 + idx,
                fetched_at=commence_time - timedelta(minutes=20),
                commence_time=commence_time,
            )
        )
        rows.append(
            _snapshot(
                event_id=event_id,
                sportsbook_key=book,
                market="h2h",
                outcome_name="BOS",
                line=None,
                price=100 + idx,
                fetched_at=commence_time - timedelta(minutes=7),
                commence_time=commence_time,
            )
        )

    db_session.add_all(rows)
    await db_session.commit()

    params = {
        "db": db_session,
        "start": datetime(2026, 1, 1, tzinfo=UTC),
        "end": datetime(2026, 2, 1, tzinfo=UTC),
        "sport_key": "basketball_nba",
        "step_seconds": 60,
        "markets": ("spreads", "totals", "h2h"),
        "lookback_minutes": 10,
        "min_books": 5,
    }

    signals_a, summary_a = await run_backtest(**params)
    signals_b, summary_b = await run_backtest(**params)

    assert len(signals_a) > 0
    assert _signal_fingerprint(signals_a) == _signal_fingerprint(signals_b)
    assert summary_a == summary_b
    assert summary_a["timestamp_field_used_counts"].get("fetched_at", 0) > 0
    assert "segments_time_bucket" in summary_a
    assert "segments_score_band" in summary_a
    assert summary_a["segments_time_bucket"]
    assert all(row["time_bucket"] == "UNKNOWN" for row in summary_a["segments_time_bucket"])
    assert all(row["score_source"] == "strength_fallback" for row in summary_a["segments_time_bucket"])

    bucket_order_map = {name: idx for idx, name in enumerate(TIME_BUCKET_ORDER)}
    source_order_map = {name: idx for idx, name in enumerate(SCORE_SOURCE_ORDER)}
    observed_bucket_order = [
        (bucket_order_map[row["time_bucket"]], source_order_map[row["score_source"]])
        for row in summary_a["segments_time_bucket"]
    ]
    assert observed_bucket_order == sorted(observed_bucket_order)

    band_order_map = {name: idx for idx, name in enumerate(SCORE_BAND_ORDER)}
    observed_band_order = [
        (band_order_map[row["score_band"]], source_order_map[row["score_source"]])
        for row in summary_a["segments_score_band"]
    ]
    assert observed_band_order == sorted(observed_band_order)


def test_segment_builders_include_unknown_bucket_and_deterministic_ordering() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    signals = [
        SimulatedSignal(
            event_id="event-1",
            signal_type="MOVE",
            market="spreads",
            outcome_name="BOS",
            created_at=now,
            direction="UP",
            strength_score=80,
            entry_line=-3.5,
            entry_price=-110,
            from_value=-4.0,
            to_value=-3.5,
            from_price=-110,
            to_price=-110,
            window_minutes=10,
            books_affected=5,
            velocity_minutes=3.0,
            metadata={"composite_score": 82, "time_bucket": "PRETIP"},
            clv_line=0.2,
            clv_prob=None,
        ),
        SimulatedSignal(
            event_id="event-2",
            signal_type="MOVE",
            market="totals",
            outcome_name="Over",
            created_at=now,
            direction="DOWN",
            strength_score=62,
            entry_line=225.0,
            entry_price=-110,
            from_value=226.0,
            to_value=225.0,
            from_price=-110,
            to_price=-110,
            window_minutes=15,
            books_affected=6,
            velocity_minutes=4.0,
            metadata={},
            clv_line=-0.1,
            clv_prob=None,
        ),
        SimulatedSignal(
            event_id="event-3",
            signal_type="KEY_CROSS",
            market="spreads",
            outcome_name="NYK",
            created_at=now,
            direction="DOWN",
            strength_score=45,
            entry_line=3.5,
            entry_price=-108,
            from_value=2.5,
            to_value=3.5,
            from_price=-108,
            to_price=-108,
            window_minutes=10,
            books_affected=5,
            velocity_minutes=2.0,
            metadata={"time_bucket": None},
            clv_line=None,
            clv_prob=0.02,
        ),
    ]

    time_segments = _build_segments_time_bucket(signals)
    score_segments = _build_segments_score_band(signals)

    assert any(row["time_bucket"] == "UNKNOWN" for row in time_segments)
    assert any(row["score_source"] == "composite" for row in time_segments)
    assert any(row["score_source"] == "strength_fallback" for row in time_segments)
    assert all(set(row.keys()) == {"time_bucket", "score_source", "count", "positive_count", "positive_rate"} for row in time_segments)
    assert all(set(row.keys()) == {"score_band", "score_source", "count", "positive_count", "positive_rate"} for row in score_segments)

    bucket_order_map = {name: idx for idx, name in enumerate(TIME_BUCKET_ORDER)}
    source_order_map = {name: idx for idx, name in enumerate(SCORE_SOURCE_ORDER)}
    assert [
        (bucket_order_map[row["time_bucket"]], source_order_map[row["score_source"]])
        for row in time_segments
    ] == sorted(
        (bucket_order_map[row["time_bucket"]], source_order_map[row["score_source"]])
        for row in time_segments
    )

    band_order_map = {name: idx for idx, name in enumerate(SCORE_BAND_ORDER)}
    assert [
        (band_order_map[row["score_band"]], source_order_map[row["score_source"]])
        for row in score_segments
    ] == sorted(
        (band_order_map[row["score_band"]], source_order_map[row["score_source"]])
        for row in score_segments
    )


async def test_backtest_summary_includes_empty_segment_keys_when_no_games(db_session: AsyncSession) -> None:
    _signals, summary = await run_backtest(
        db=db_session,
        start=datetime(2026, 3, 1, tzinfo=UTC),
        end=datetime(2026, 3, 2, tzinfo=UTC),
        sport_key="basketball_nba",
        step_seconds=60,
        markets=("spreads", "totals", "h2h"),
        lookback_minutes=10,
        min_books=5,
    )
    assert summary["games_processed"] == 0
    assert "segments_time_bucket" in summary
    assert "segments_score_band" in summary
    assert summary["segments_time_bucket"] == []
    assert summary["segments_score_band"] == []


def test_timestamp_fallback_priority() -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    row_fetched = SimpleNamespace(
        id="row-fetched",
        fetched_at=base + timedelta(minutes=1),
        created_at=base - timedelta(minutes=2),
        updated_at=base - timedelta(minutes=1),
    )
    ts_fetched, field_fetched, row_id_fetched = resolve_snapshot_ordering(row_fetched)
    assert field_fetched == "fetched_at"
    assert ts_fetched == base + timedelta(minutes=1)
    assert row_id_fetched == "row-fetched"

    row_created = SimpleNamespace(
        id="row-created",
        fetched_at=None,
        created_at=base + timedelta(minutes=3),
        updated_at=base + timedelta(minutes=4),
    )
    ts_created, field_created, _ = resolve_snapshot_ordering(row_created)
    assert field_created == "created_at"
    assert ts_created == base + timedelta(minutes=3)

    row_updated = SimpleNamespace(
        id="row-updated",
        fetched_at=None,
        created_at=None,
        updated_at=base + timedelta(minutes=5),
    )
    ts_updated, field_updated, _ = resolve_snapshot_ordering(row_updated)
    assert field_updated == "updated_at"
    assert ts_updated == base + timedelta(minutes=5)

    row_pk_only = SimpleNamespace(id="row-pk-only")
    ts_pk, field_pk, row_id_pk = resolve_snapshot_ordering(row_pk_only)
    assert field_pk == "primary_key"
    assert ts_pk is None
    assert row_id_pk == "row-pk-only"

    ordering_tuple = snapshot_ordering_tuple(row_pk_only, fallback_timestamp=base)
    assert ordering_tuple == (base, "row-pk-only")
