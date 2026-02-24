from datetime import datetime
from typing import Literal
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
    game_label: str | None
    game_commence_time: datetime | None
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
    freshness_seconds: int
    freshness_bucket: str
    lifecycle_stage: str
    lifecycle_reason: str
    alert_decision: str
    alert_reason: str
    metadata: dict


class SignalLifecycleReasonCount(BaseModel):
    reason: str
    count: int


class SignalLifecycleSummary(BaseModel):
    days: int
    total_detected: int
    eligible_signals: int
    sent_signals: int
    filtered_signals: int
    stale_signals: int
    not_sent_signals: int
    top_filtered_reasons: list[SignalLifecycleReasonCount]


class SignalQualityWeeklySummary(BaseModel):
    days: int
    total_signals: int
    eligible_signals: int
    hidden_signals: int
    sent_rate_pct: float
    avg_strength: float | None
    clv_samples: int
    clv_pct_positive: float
    top_hidden_reason: str | None


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


class OpportunityPoint(BaseModel):
    signal_id: UUID
    event_id: str
    game_label: str | None
    game_commence_time: datetime | None
    signal_type: str
    market: str
    outcome_name: str | None
    direction: str
    strength_score: int
    created_at: datetime
    best_book_key: str | None
    best_line: float | None
    best_price: int | None
    consensus_line: float | None
    consensus_price: float | None
    best_delta: float | None
    best_edge_line: float | None
    best_edge_prob: float | None
    market_width: float | None
    delta_type: str
    books_considered: int
    freshness_seconds: int | None
    freshness_bucket: str
    execution_rank: int
    clv_prior_samples: int | None
    clv_prior_pct_positive: float | None
    opportunity_score: int
    context_score: int | None
    blended_score: int | None
    ranking_score: int
    score_basis: Literal["opportunity", "blended"]
    score_components: dict[str, int]
    score_summary: str
    opportunity_status: str
    reason_tags: list[str]
    actionable_reason: str


class OpportunityTeaserPoint(BaseModel):
    event_id: str
    game_label: str | None
    game_commence_time: datetime | None
    signal_type: str
    market: str
    outcome_name: str | None
    direction: str
    strength_score: int
    created_at: datetime
    freshness_bucket: str
    books_considered: int
    opportunity_status: str


class PublicTeaserOpportunityPoint(BaseModel):
    game_label: str | None
    commence_time: datetime | None
    signal_type: str
    market: str
    outcome_name: str | None
    score_status: Literal["ACTIONABLE", "MONITOR", "STALE"]
    freshness_label: Literal["Fresh", "Aging", "Stale"]
    delta_display: str


class PublicTeaserKpis(BaseModel):
    signals_in_window: int
    books_tracked_estimate: int
    pct_actionable: float
    pct_fresh: float
    updated_at: datetime


class TeaserInteractionEventIn(BaseModel):
    event_name: Literal["viewed_teaser", "clicked_upgrade_from_teaser"]
    source: str | None = None
    sport_key: str | None = None


class TeaserInteractionEventOut(BaseModel):
    status: str
