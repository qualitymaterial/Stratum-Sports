import os
from functools import lru_cache
from typing import Mapping
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DATABASE_URL_PLACEHOLDER = "REPLACE_WITH_STRONG_DB_PASSWORD"

BOOK_TIERS: dict[str, str] = {
    "pinnacle": "T1",
    "circa": "T1",
    "betcris": "T2",
    "draftkings": "T3",
    "fanduel": "T3",
}

DEFAULT_BOOK_TIER = "T3"


def venue_tier(venue: str) -> str:
    if not venue:
        return DEFAULT_BOOK_TIER
    return BOOK_TIERS.get(venue.lower(), DEFAULT_BOOK_TIER)


def get_venue_tier(venue: str) -> str:
    return venue_tier(venue)


def resolve_database_url(
    *,
    database_url: str | None,
    postgres_user: str | None,
    postgres_password: str | None,
    postgres_host: str | None = "db",
    postgres_port: int | str | None = "5432",
    postgres_db: str | None = "stratum_sports",
) -> tuple[str, str]:
    raw_database_url = (database_url or "").strip()
    if raw_database_url and DATABASE_URL_PLACEHOLDER not in raw_database_url:
        return raw_database_url, "env"

    user = quote_plus((postgres_user or "stratum").strip())
    password = quote_plus((postgres_password or "stratum").strip())
    host = (postgres_host or "db").strip() or "db"
    port = str(postgres_port or "5432").strip() or "5432"
    db_name = (postgres_db or "stratum_sports").strip() or "stratum_sports"
    constructed = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
    return constructed, "postgres_fallback"


def resolve_database_url_from_env(
    env: Mapping[str, str] | None = None,
    *,
    default_database_url: str | None = None,
) -> tuple[str, str]:
    source_env = os.environ if env is None else env
    database_url = source_env.get("DATABASE_URL", default_database_url or "")
    return resolve_database_url(
        database_url=database_url,
        postgres_user=source_env.get("POSTGRES_USER"),
        postgres_password=source_env.get("POSTGRES_PASSWORD"),
        postgres_host=source_env.get("POSTGRES_HOST", "db"),
        postgres_port=source_env.get("POSTGRES_PORT", "5432"),
        postgres_db=source_env.get("POSTGRES_DB", "stratum_sports"),
    )


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
    password_reset_token_expire_minutes: int = 30

    database_url: str = ""
    postgres_user: str = "stratum"
    postgres_password: str = "stratum"
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "stratum_sports"
    redis_url: str = "redis://redis:6379/0"

    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:3000/auth/discord/callback"
    discord_webhook_allowed_hosts: str = "discord.com,ptb.discord.com,canary.discord.com"

    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_poll_interval_seconds: int = 60
    odds_poll_interval_idle_seconds: int = 300
    odds_poll_interval_low_credit_seconds: int = 900
    odds_api_low_credit_threshold: int = 200
    odds_api_target_daily_credits: int = 1200
    odds_api_sport_keys: str = "basketball_nba,basketball_ncaab,americanfootball_nfl"
    odds_api_regions: str = "us"
    odds_api_markets: str = "spreads,totals,h2h"
    odds_api_bookmakers: str = ""
    odds_api_retry_attempts: int = 3
    odds_api_retry_backoff_seconds: float = 1.0
    odds_api_retry_backoff_max_seconds: float = 8.0
    odds_api_circuit_failures_to_open: int = 3
    odds_api_circuit_open_seconds: int = 120
    stratum_close_capture_enabled: bool = True
    stratum_close_capture_max_events_per_cycle: int = 10
    nba_key_numbers: str = "2,3,4,5,6,7,8,10"

    free_delay_minutes: int = 10
    free_watchlist_limit: int = 3

    injury_feed_provider: str = "heuristic"
    sportsdataio_api_key: str = ""
    sportsdataio_base_url: str = "https://api.sportsdata.io/v3"
    sportsdataio_injuries_endpoint_nba: str = ""
    sportsdataio_injuries_endpoint_ncaab: str = ""
    sportsdataio_injuries_endpoint_nfl: str = ""
    sportsdataio_nfl_injuries_season: str = ""
    sportsdataio_nfl_injuries_week: str = ""
    sportsdataio_timeout_seconds: float = 8.0
    sportsdataio_cache_seconds: int = 180

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
    enable_historical_backfill: bool = True
    historical_backfill_lookback_hours: int = 72
    historical_backfill_interval_minutes: int = 60
    clv_close_cutoff: str = "TIPOFF"
    historical_backfill_max_games_per_run: int = 25
    kpi_enabled: bool = True
    kpi_retention_days: int = 30
    kpi_write_failures_soft: bool = True
    performance_ui_enabled: bool = True
    actionable_book_card_enabled: bool = True
    performance_default_days: int = 30
    performance_max_limit: int = 200
    signal_filter_default_min_strength: int = 60
    public_structural_core_mode: bool = True
    time_bucket_expose_inplay: bool = True
    actionable_book_max_books: int = 8
    free_teaser_enabled: bool = True
    context_score_blend_enabled: bool = False
    context_score_blend_weight_opportunity: float = 0.8
    context_score_blend_weight_context: float = 0.2
    context_score_weight_injuries: float = 0.5
    context_score_weight_player_props: float = 0.3
    context_score_weight_pace: float = 0.2
    context_score_weight_cross_market: float = 0.20

    # ── Exchange divergence signal settings ────────────────────────
    exchange_divergence_signal_enabled: bool = True
    exchange_divergence_lookback_minutes: int = 15
    exchange_divergence_cooldown_seconds: int = 900
    exchange_divergence_max_signals_per_event: int = 2

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

    # ── Exchange adapter settings ─────────────────────────────────
    kalshi_api_key: str = ""
    kalshi_base_url: str = "https://api.elections.kalshi.com"
    kalshi_timeout_seconds: float = 5.0
    max_kalshi_markets_per_cycle: int = 10

    enable_polymarket_ingest: bool = False
    polymarket_base_url: str = "https://clob.polymarket.com"
    polymarket_timeout_seconds: float = 5.0
    max_polymarket_markets_per_cycle: int = 10

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

    @property
    def discord_webhook_allowed_hosts_list(self) -> list[str]:
        return [v.strip().lower() for v in self.discord_webhook_allowed_hosts.split(",") if v.strip()]

    @property
    def odds_api_sport_keys_list(self) -> list[str]:
        values = [v.strip() for v in self.odds_api_sport_keys.split(",") if v.strip()]
        return values or ["basketball_nba"]

    @property
    def resolved_database_url(self) -> str:
        url, _source = resolve_database_url(
            database_url=self.database_url,
            postgres_user=self.postgres_user,
            postgres_password=self.postgres_password,
            postgres_host=self.postgres_host,
            postgres_port=self.postgres_port,
            postgres_db=self.postgres_db,
        )
        return url

    @property
    def resolved_database_url_source(self) -> str:
        _url, source = resolve_database_url(
            database_url=self.database_url,
            postgres_user=self.postgres_user,
            postgres_password=self.postgres_password,
            postgres_host=self.postgres_host,
            postgres_port=self.postgres_port,
            postgres_db=self.postgres_db,
        )
        return source


@lru_cache
def get_settings() -> Settings:
    return Settings()
