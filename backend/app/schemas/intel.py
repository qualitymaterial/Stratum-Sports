from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConsensusPoint(BaseModel):
    event_id: str
    market: str
    outcome_name: str
    consensus_line: float | None
    consensus_price: float | None
    dispersion: float | None
    books_count: int
    fetched_at: datetime


class ClvRecordPoint(BaseModel):
    signal_id: UUID
    event_id: str
    signal_type: str
    market: str
    outcome_name: str
    strength_score: int
    entry_line: float | None
    entry_price: float | None
    close_line: float | None
    close_price: float | None
    clv_line: float | None
    clv_prob: float | None
    computed_at: datetime


class ClvSummaryPoint(BaseModel):
    signal_type: str
    market: str
    count: int
    pct_positive_clv: float
    avg_clv_line: float | None
    avg_clv_prob: float | None
