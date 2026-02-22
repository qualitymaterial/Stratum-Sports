from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.models.user import User


settings = get_settings()


def delayed_cutoff_for_user(user: User) -> datetime | None:
    if is_pro(user):
        return None
    return datetime.now(UTC) - timedelta(minutes=settings.free_delay_minutes)


def is_pro(user: User) -> bool:
    return user.tier == "pro" or user.is_admin
