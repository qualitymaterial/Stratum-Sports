from app.core.config import resolve_database_url


def test_placeholder_database_url_uses_postgres_fallback() -> None:
    resolved, source = resolve_database_url(
        database_url="postgresql+asyncpg://app:REPLACE_WITH_STRONG_DB_PASSWORD@db:5432/stratum_sports",
        postgres_user="stratum_prod",
        postgres_password="safe-password",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="stratum_sports",
    )

    assert source == "postgres_fallback"
    assert resolved == "postgresql+asyncpg://stratum_prod:safe-password@db:5432/stratum_sports"


def test_special_characters_in_credentials_are_url_encoded() -> None:
    resolved, source = resolve_database_url(
        database_url="",
        postgres_user="user+name",
        postgres_password="P@ss:w/rd! 123",
        postgres_host="postgres.internal",
        postgres_port="5432",
        postgres_db="sports_db",
    )

    assert source == "postgres_fallback"
    assert resolved == "postgresql+asyncpg://user%2Bname:P%40ss%3Aw%2Frd%21+123@postgres.internal:5432/sports_db"


def test_normal_database_url_is_respected() -> None:
    resolved, source = resolve_database_url(
        database_url="postgresql+asyncpg://custom_user:custom_pass@prod-db:5432/custom_db",
        postgres_user="ignored",
        postgres_password="ignored",
        postgres_host="ignored",
        postgres_port=5432,
        postgres_db="ignored",
    )

    assert source == "env"
    assert resolved == "postgresql+asyncpg://custom_user:custom_pass@prod-db:5432/custom_db"
