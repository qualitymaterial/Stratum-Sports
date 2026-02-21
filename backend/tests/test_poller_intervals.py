from app.tasks.poller import determine_poll_interval, settings


def test_poll_interval_defaults_to_active_when_no_cycle_result() -> None:
    assert determine_poll_interval(None) == settings.odds_poll_interval_seconds


def test_poll_interval_uses_idle_when_no_events_seen() -> None:
    result = {"events_seen": 0, "api_requests_remaining": settings.odds_api_low_credit_threshold + 1}
    assert determine_poll_interval(result) == settings.odds_poll_interval_idle_seconds


def test_poll_interval_uses_low_credit_when_remaining_is_low() -> None:
    result = {"events_seen": 12, "api_requests_remaining": settings.odds_api_low_credit_threshold}
    assert determine_poll_interval(result) == settings.odds_poll_interval_low_credit_seconds
