from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DiscordThresholds(BaseModel):
    min_books_affected: int = Field(default=1, ge=1, le=50)
    max_dispersion: float | None = Field(default=None, ge=0)
    cooldown_minutes: int = Field(default=15, ge=0, le=1440)


class DiscordConnectionUpsert(BaseModel):
    webhook_url: str
    is_enabled: bool = True
    alert_spreads: bool = True
    alert_totals: bool = True
    alert_multibook: bool = True
    min_strength: int = Field(default=60, ge=1, le=100)
    thresholds: DiscordThresholds = Field(default_factory=DiscordThresholds)


class DiscordConnectionOut(BaseModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: UUID
    webhook_url: str
    is_enabled: bool
    alert_spreads: bool
    alert_totals: bool
    alert_multibook: bool
    min_strength: int
    thresholds: dict = Field(validation_alias="thresholds_json")
    created_at: datetime
    updated_at: datetime
