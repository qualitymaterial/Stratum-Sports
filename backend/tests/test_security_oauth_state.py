from app.core.security import create_oauth_state_token, decode_oauth_state_token


def test_oauth_state_roundtrip() -> None:
    token = create_oauth_state_token(provider="discord")
    payload = decode_oauth_state_token(token, provider="discord")
    assert payload is not None
    assert payload["type"] == "oauth_state"
    assert payload["provider"] == "discord"
    assert isinstance(payload.get("nonce"), str)


def test_oauth_state_wrong_provider_rejected() -> None:
    token = create_oauth_state_token(provider="discord")
    assert decode_oauth_state_token(token, provider="google") is None


def test_oauth_state_invalid_token_rejected() -> None:
    assert decode_oauth_state_token("not-a-valid-token", provider="discord") is None
