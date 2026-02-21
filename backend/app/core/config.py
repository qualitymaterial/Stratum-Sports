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

    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_poll_interval_seconds: int = 60
    nba_key_numbers: str = "2,3,4,5,6,7,8,10"

    free_delay_minutes: int = 10
    free_watchlist_limit: int = 3

    snapshot_retention_hours: int = 48
    signal_retention_days: int = 30

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
