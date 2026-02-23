from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CycleKpiOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    cycle_id: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    requests_used_delta: int | None
    requests_remaining: int | None
    requests_limit: int | None
    events_processed: int | None
    snapshots_inserted: int | None
    consensus_points_written: int | None
    signals_created_total: int | None
    signals_created_by_type: dict[str, int] | None
    alerts_sent: int | None
    alerts_failed: int | None
    error: str | None
    degraded: bool
    notes: dict | None
    created_at: datetime


class SignalTypeCount(BaseModel):
    signal_type: str
    count: int


class CycleSummaryOut(BaseModel):
    total_cycles: int
    avg_duration_ms: float | None
    total_snapshots_inserted: int
    total_signals_created: int
    alerts_sent: int
    alerts_failed: int
    requests_used_delta: int
    top_signal_types: list[SignalTypeCount]


class OperatorOpsMetrics(BaseModel):
    total_cycles: int
    avg_cycle_duration_ms: float | None
    degraded_cycles: int
    total_requests_used: int
    avg_requests_remaining: float | None = None
    total_snapshots_inserted: int
    total_consensus_points_written: int
    total_signals_created: int
    signals_created_by_type: dict[str, int]


class ClvBySignalTypeItem(BaseModel):
    signal_type: str
    count: int
    pct_positive: float
    avg_clv_line: float | None
    avg_clv_prob: float | None


class ClvByMarketItem(BaseModel):
    market: str
    count: int
    pct_positive: float
    avg_clv_line: float | None
    avg_clv_prob: float | None


class OperatorPerformanceMetrics(BaseModel):
    clv_by_signal_type: list[ClvBySignalTypeItem]
    clv_by_market: list[ClvByMarketItem]


class OperatorReliabilityMetrics(BaseModel):
    alerts_sent: int
    alerts_failed: int
    alert_failure_rate: float


class OperatorReport(BaseModel):
    days: int
    period_start: datetime
    period_end: datetime
    ops: OperatorOpsMetrics
    performance: OperatorPerformanceMetrics
    reliability: OperatorReliabilityMetrics


class AdminOverviewOut(BaseModel):
    report: OperatorReport
    recent_cycles: list[CycleKpiOut]
