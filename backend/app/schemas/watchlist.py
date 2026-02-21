from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WatchlistOut(BaseModel):
    id: UUID
    event_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
