from app.services.time_bucket import compute_time_bucket


def test_compute_time_bucket_edges() -> None:
    assert compute_time_bucket(None) == "UNKNOWN"
    assert compute_time_bucket(-1) == "INPLAY"
    assert compute_time_bucket(0) == "PRETIP"
    assert compute_time_bucket(29.9) == "PRETIP"
    assert compute_time_bucket(30) == "LATE"
    assert compute_time_bucket(119.9) == "LATE"
    assert compute_time_bucket(120) == "MID"
    assert compute_time_bucket(359.9) == "MID"
    assert compute_time_bucket(360) == "OPEN"

