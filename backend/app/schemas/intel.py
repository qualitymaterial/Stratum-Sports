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


class ClvRecapRow(BaseModel):
    period_start: datetime
    signal_type: str
    market: str
    count: int
    pct_positive_clv: float
    avg_clv_line: float | None
    avg_clv_prob: float | None


class ClvRecapResponse(BaseModel):
    days: int
    grain: str
    rows: list[ClvRecapRow]


class ClvTrustScorecard(BaseModel):
    signal_type: str
    market: str
    count: int
    pct_positive_clv: float
    avg_clv_line: float | None
    avg_clv_prob: float | None
    stddev_clv_line: float | None
    stddev_clv_prob: float | None
    confidence_score: int
    confidence_tier: str
    stability_ratio_line: float | None
    stability_ratio_prob: float | None
    stability_label: str
    score_components: dict[str, int]


class ClvTeaserResponse(BaseModel):
    days: int
    total_records: int
    rows: list[ClvSummaryPoint]


class SignalQualityPoint(BaseModel):
    id: UUID
    event_id: str
    market: str
    signal_type: str
    direction: str
    strength_score: int
    books_affected: int
    window_minutes: int
    created_at: datetime
    outcome_name: str | None
    book_key: str | None
    delta: float | None
    dispersion: float | None
    metadata: dict


class ActionableBookQuote(BaseModel):
    sportsbook_key: str
    line: float | None
    price: int
    fetched_at: datetime
    delta: float | None


class ActionableBookCard(BaseModel):
    event_id: str
    signal_id: UUID
    signal_type: str
    market: str
    outcome_name: str | None
    direction: str
    strength_score: int
    consensus_line: float | None
    consensus_price: float | None
    dispersion: float | None
    consensus_source: str
    best_book_key: str | None
    best_line: float | None
    best_price: int | None
    best_delta: float | None
    delta_type: str
    fetched_at: datetime | None
    freshness_seconds: int | None
    freshness_bucket: str
    is_stale: bool
    execution_rank: int
    actionable_reason: str
    books_considered: int
    top_books: list[ActionableBookQuote]
    quotes: list[ActionableBookQuote]
