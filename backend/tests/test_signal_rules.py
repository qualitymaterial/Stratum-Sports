from app.services.signals import (
    compute_strength_score,
    crosses_key_number,
    should_trigger_spread_move,
    should_trigger_total_move,
)


def test_spread_move_triggers_on_half_point() -> None:
    triggered, signal_type, key_cross, magnitude = should_trigger_spread_move(
        from_value=-4.0,
        to_value=-4.5,
        key_numbers=[2, 3, 4, 5],
    )
    assert triggered is True
    assert signal_type == "MOVE"
    assert key_cross is False
    assert magnitude == 0.5


def test_spread_move_triggers_on_key_cross_even_with_small_move() -> None:
    triggered, signal_type, key_cross, magnitude = should_trigger_spread_move(
        from_value=-2.9,
        to_value=-3.1,
        key_numbers=[2, 3, 4, 5],
    )
    assert triggered is True
    assert signal_type == "KEY_CROSS"
    assert key_cross is True
    assert round(magnitude, 1) == 0.2


def test_total_move_threshold() -> None:
    triggered_small, magnitude_small = should_trigger_total_move(224.5, 225.2)
    triggered_large, magnitude_large = should_trigger_total_move(224.5, 225.6)

    assert triggered_small is False
    assert round(magnitude_small, 1) == 0.7
    assert triggered_large is True
    assert round(magnitude_large, 1) == 1.1


def test_key_cross_helper() -> None:
    assert crosses_key_number(-2.5, -4.0, [2, 3, 4, 5]) is True
    assert crosses_key_number(-2.1, -2.4, [2, 3, 4, 5]) is False


def test_strength_score_clamped() -> None:
    score_high, components_high = compute_strength_score(
        magnitude=10,
        velocity_minutes=0.5,
        window_minutes=10,
        books_affected=8,
    )
    score_low, components_low = compute_strength_score(
        magnitude=0.01,
        velocity_minutes=10,
        window_minutes=10,
        books_affected=1,
    )

    assert 95 <= score_high <= 100
    assert 1 <= score_low <= 100
    assert set(components_high.keys()) == {
        "magnitude_component",
        "speed_component",
        "books_component",
    }
    assert set(components_low.keys()) == {
        "magnitude_component",
        "speed_component",
        "books_component",
    }


def test_strength_score_rewards_earlier_timing() -> None:
    early_score, early_components = compute_strength_score(
        magnitude=1.2,
        velocity_minutes=2.0,
        window_minutes=10,
        books_affected=4,
        minutes_to_tip=180.0,
    )
    late_score, late_components = compute_strength_score(
        magnitude=1.2,
        velocity_minutes=2.0,
        window_minutes=10,
        books_affected=4,
        minutes_to_tip=10.0,
    )

    assert early_score > late_score
    assert early_components["timing_component"] > late_components["timing_component"]
