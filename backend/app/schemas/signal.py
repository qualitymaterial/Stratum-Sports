from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SignalOut(BaseModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: UUID
    event_id: str
    market: str
    signal_type: str
    display_type: str | None = None
    direction: str
    from_value: float
    to_value: float
    from_price: int | None
    to_price: int | None
    window_minutes: int
    books_affected: int
    velocity_minutes: float | None
    time_bucket: str | None = None
    strength_score: int
    created_at: datetime
    metadata: dict = Field(validation_alias="metadata_json")
