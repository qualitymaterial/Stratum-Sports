from app.services.composite_score import (
    compute_composite_score,
    normalize,
    time_bonus_from_bucket,
)


def test_composite_score_is_bounded_between_zero_and_hundred() -> None:
    assert 0 <= compute_composite_score(-10.0, None, False, 5000) <= 100
    assert 0 <= compute_composite_score(100.0, 100.0, True, 1) <= 100


def test_composite_score_monotonic_with_move_strength() -> None:
    low = compute_composite_score(0.3, 0.01, False, 500)
    high = compute_composite_score(1.5, 0.01, False, 500)
    assert high >= low


def test_key_cross_bonus_increases_score() -> None:
    without_bonus = compute_composite_score(1.0, 0.02, False, 500)
    with_bonus = compute_composite_score(1.0, 0.02, True, 500)
    assert with_bonus > without_bonus


def test_pretip_bonus_higher_than_open_for_same_inputs() -> None:
    pretip = compute_composite_score(1.0, 0.02, False, 30)
    open_score = compute_composite_score(1.0, 0.02, False, 2000)
    assert pretip > open_score


def test_normalize_clamps_and_time_bonus_mapping() -> None:
    assert normalize(-1.0, 0.25, 2.0) == 0.0
    assert normalize(5.0, 0.25, 2.0) == 1.0
    assert time_bonus_from_bucket("PRETIP") == 0.05
    assert time_bonus_from_bucket("LATE") == 0.03
    assert time_bonus_from_bucket("MID") == 0.01
    assert time_bonus_from_bucket("OPEN") == 0.0
