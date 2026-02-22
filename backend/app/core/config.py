from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env == "production" and self.jwt_secret in {"change-me", ""}:
            raise ValueError(
                "JWT_SECRET must be set to a secure random value in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if self.app_env == "production" and self.ops_internal_token in {"", "dev-ops-token", "change-me-ops-token"}:
            raise ValueError(
                "OPS_INTERNAL_TOKEN must be set to a secure internal token in production."
            )
        return self

    app_env: str = "development"
    app_name: str = "Stratum Sports API"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    cors_origins: str = "http://localhost:3000"
    trusted_proxies: str = "127.0.0.1"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    database_url: str = "postgresql+asyncpg://stratum:stratum@db:5432/stratum_sports"
    redis_url: str = "redis://redis:6379/0"

    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:3000/auth/discord/callback"

    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_poll_interval_seconds: int = 60
    odds_poll_interval_idle_seconds: int = 300
    odds_poll_interval_low_credit_seconds: int = 900
    odds_api_low_credit_threshold: int = 200
    odds_api_target_daily_credits: int = 1200
    odds_api_regions: str = "us"
    odds_api_markets: str = "spreads,totals,h2h"
    odds_api_bookmakers: str = ""
    stratum_close_capture_enabled: bool = True
    stratum_close_capture_max_events_per_cycle: int = 10
    nba_key_numbers: str = "2,3,4,5,6,7,8,10"

    free_delay_minutes: int = 10
    free_watchlist_limit: int = 3

    snapshot_retention_hours: int = 48
    signal_retention_days: int = 30
    consensus_enabled: bool = True
    consensus_lookback_minutes: int = 10
    consensus_min_books: int = 5
    consensus_markets: str = "spreads,totals,h2h"
    consensus_retention_days: int = 14
    dislocation_enabled: bool = True
    dislocation_lookback_minutes: int = 10
    dislocation_min_books: int = 5
    dislocation_spread_line_delta: float = 1.0
    dislocation_total_line_delta: float = 2.0
    dislocation_ml_implied_prob_delta: float = 0.03
    dislocation_cooldown_seconds: int = 900
    dislocation_max_signals_per_event: int = 6
    steam_enabled: bool = True
    steam_window_minutes: int = 3
    steam_min_books: int = 4
    steam_min_move_spread: float = 0.5
    steam_min_move_total: float = 1.0
    steam_cooldown_seconds: int = 900
    steam_max_signals_per_event: int = 4
    steam_discord_enabled: bool = False
    clv_enabled: bool = True
    clv_minutes_after_commence: int = 10
    clv_lookback_days: int = 7
    clv_retention_days: int = 60
    clv_job_interval_minutes: int = 60
    kpi_enabled: bool = True
    kpi_retention_days: int = 30
    kpi_write_failures_soft: bool = True
    ops_internal_token: str = "dev-ops-token"
    ops_digest_enabled: bool = False
    ops_digest_webhook_url: str = ""
    ops_digest_weekday: int = 1
    ops_digest_hour_utc: int = 13
    ops_digest_minute_utc: int = 0
    ops_digest_lookback_days: int = 7

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = "price_pro_placeholder"
    stripe_success_url: str = "http://localhost:3000/app/dashboard?billing=success"
    stripe_cancel_url: str = "http://localhost:3000/app/dashboard?billing=cancel"

    @property
    def cors_origins_list(self) -> list[str]:
        return [v.strip() for v in self.cors_origins.split(",") if v.strip()]

    @property
    def nba_key_numbers_list(self) -> list[float]:
        return [float(v.strip()) for v in self.nba_key_numbers.split(",") if v.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [v.strip() for v in self.trusted_proxies.split(",") if v.strip()]

    @property
    def consensus_markets_list(self) -> list[str]:
        return [v.strip() for v in self.consensus_markets.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
