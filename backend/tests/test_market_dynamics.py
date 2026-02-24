from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.market_dynamics import (
    build_line_series_from_snapshots,
    compute_acceleration,
    compute_velocity,
    get_time_bucket,
)


def test_get_time_bucket_boundaries() -> None:
    assert get_time_bucket(60) == "PRETIP"
    assert get_time_bucket(61) == "LATE"
    assert get_time_bucket(360) == "LATE"
    assert get_time_bucket(361) == "MID"
    assert get_time_bucket(1440) == "MID"
    assert get_time_bucket(1441) == "OPEN"


def test_compute_velocity_two_points_over_ten_minutes() -> None:
    start = datetime(2026, 2, 24, 12, 0, tzinfo=UTC)
    points = [
        (start, -3.5),
        (start + timedelta(minutes=10), -2.5),
    ]
    velocity = compute_velocity(points)
    assert velocity == 0.1


def test_compute_velocity_invalid_or_insufficient_points() -> None:
    now = datetime(2026, 2, 24, 12, 0, tzinfo=UTC)
    assert compute_velocity([]) is None
    assert compute_velocity([(now, -3.5)]) is None
    assert compute_velocity([(now, -3.5), (now, -2.5)]) is None


def test_compute_acceleration_valid_and_edge_cases() -> None:
    start = datetime(2026, 2, 24, 12, 0, tzinfo=UTC)
    points = [
        (start, -4.0),
        (start + timedelta(minutes=10), -3.0),
        (start + timedelta(minutes=20), -1.0),
        (start + timedelta(minutes=30), 0.0),
    ]
    # v1 = |-3 - (-4)| / 10 = 0.1
    # v2 = |0 - (-1)| / 10 = 0.1
    assert compute_acceleration(points) == 0.0

    assert compute_acceleration(points[:2]) is None
    assert compute_acceleration(
        [
            (start, -4.0),
            (start, -3.0),
            (start, -2.0),
        ]
    ) is None


def test_build_line_series_from_snapshots_sorted_and_filtered() -> None:
    start = datetime(2026, 2, 24, 12, 0, tzinfo=UTC)
    snapshots = [
        SimpleNamespace(fetched_at=start + timedelta(minutes=2), line=-2.0),
        SimpleNamespace(fetched_at=start, line=-4.0),
        SimpleNamespace(fetched_at=start + timedelta(minutes=1), line=-3.0),
        SimpleNamespace(fetched_at=start + timedelta(minutes=3), line=None),
        SimpleNamespace(fetched_at=None, line=-1.0),
        {"fetched_at": start + timedelta(minutes=4), "line": -0.5},
    ]

    points = build_line_series_from_snapshots(snapshots)
    assert points == [
        (start, -4.0),
        (start + timedelta(minutes=1), -3.0),
        (start + timedelta(minutes=2), -2.0),
        (start + timedelta(minutes=4), -0.5),
    ]
