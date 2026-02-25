from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class ConversionBySportOut(BaseModel):
    sport_key: str
    teaser_views: int
    teaser_clicks: int
    click_through_rate: float


class ConversionFunnelOut(BaseModel):
    days: int
    period_start: datetime
    period_end: datetime
    teaser_views: int
    teaser_clicks: int
    click_through_rate: float
    unique_viewers: int
    unique_clickers: int
    by_sport: list[ConversionBySportOut]


class AdminOverviewOut(BaseModel):
    report: OperatorReport
    recent_cycles: list[CycleKpiOut]
    conversion: ConversionFunnelOut


class AdminOutcomesKpiSetOut(BaseModel):
    clv_samples: int
    positive_count: int
    negative_count: int
    clv_positive_rate: float
    avg_clv_line: float | None
    avg_clv_prob: float | None
    sent_rate: float
    stale_rate: float
    degraded_cycle_rate: float
    alert_failure_rate: float


class AdminOutcomesDeltaOut(BaseModel):
    clv_samples_delta: int
    positive_count_delta: int
    negative_count_delta: int
    clv_positive_rate_delta: float
    avg_clv_line_delta: float | None
    avg_clv_prob_delta: float | None
    sent_rate_delta: float
    stale_rate_delta: float
    degraded_cycle_rate_delta: float
    alert_failure_rate_delta: float


class AdminOutcomesBreakdownRowOut(BaseModel):
    name: str
    count: int
    positive_rate: float
    avg_clv_line: float | None
    avg_clv_prob: float | None


class AdminOutcomesFilteredReasonRowOut(BaseModel):
    reason: str
    count: int


class AdminOutcomesReportOut(BaseModel):
    period_start: datetime
    period_end: datetime
    baseline_period_start: datetime
    baseline_period_end: datetime
    kpis: AdminOutcomesKpiSetOut
    baseline_kpis: AdminOutcomesKpiSetOut
    delta_vs_baseline: AdminOutcomesDeltaOut
    status: str
    status_reason: str
    by_signal_type: list[AdminOutcomesBreakdownRowOut]
    by_market: list[AdminOutcomesBreakdownRowOut]
    top_filtered_reasons: list[AdminOutcomesFilteredReasonRowOut]


class AdminUserSearchItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    email: str
    tier: str
    is_active: bool
    is_admin: bool
    admin_role: str | None
    created_at: datetime


class AdminUserSearchListOut(BaseModel):
    total: int
    limit: int
    items: list[AdminUserSearchItemOut]


class AdminUserTierUpdateRequest(BaseModel):
    tier: Literal["free", "pro"]
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminUserTierUpdateOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    old_tier: str
    new_tier: str
    reason: str


class AdminUserRoleUpdateRequest(BaseModel):
    admin_role: Literal["super_admin", "ops_admin", "support_admin", "billing_admin"] | None = None
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminUserRoleUpdateOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    old_admin_role: str | None
    new_admin_role: str | None
    old_is_admin: bool
    new_is_admin: bool
    reason: str


class AdminUserActiveUpdateRequest(BaseModel):
    is_active: bool
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminUserActiveUpdateOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    old_is_active: bool
    new_is_active: bool
    reason: str


class AdminUserPasswordResetRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminUserPasswordResetOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    reason: str
    message: str
    reset_token: str | None = None
    expires_in_minutes: int | None = None


class AdminBillingSubscriptionOut(BaseModel):
    id: UUID
    stripe_subscription_id: str
    stripe_price_id: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminUserBillingOverviewOut(BaseModel):
    user_id: UUID
    email: str
    tier: str
    is_active: bool
    stripe_customer_id: str | None
    subscription: AdminBillingSubscriptionOut | None


class AdminBillingMutationRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminBillingMutationOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    reason: str
    operation: Literal["resync", "cancel", "reactivate"]
    previous_status: str | None = None
    new_status: str | None = None
    previous_cancel_at_period_end: bool | None = None
    new_cancel_at_period_end: bool | None = None
    subscription_id: str | None = None


class AdminApiPartnerKeyOut(BaseModel):
    id: UUID
    user_id: UUID
    created_by_user_id: UUID | None
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminApiPartnerKeyListOut(BaseModel):
    user_id: UUID
    email: str
    tier: str
    total_keys: int
    active_keys: int
    recently_used_30d: int
    items: list[AdminApiPartnerKeyOut]


class AdminApiPartnerKeyIssueRequest(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminApiPartnerKeyRotateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=64)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminApiPartnerKeyMutationRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)


class AdminApiPartnerKeyIssueOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    reason: str
    operation: Literal["issue", "rotate"]
    key: AdminApiPartnerKeyOut
    api_key: str


class AdminApiPartnerKeyRevokeOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    reason: str
    operation: Literal["revoke"]
    key_id: UUID
    key_prefix: str
    old_is_active: bool
    new_is_active: bool
    revoked_at: datetime | None


class AdminApiPartnerEntitlementOut(BaseModel):
    entitlement_id: UUID | None = None
    user_id: UUID
    email: str
    plan_code: Literal["api_monthly", "api_annual"] | None = None
    api_access_enabled: bool
    soft_limit_monthly: int | None = None
    overage_enabled: bool
    overage_price_cents: int | None = None
    overage_unit_quantity: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminApiPartnerEntitlementUpdateRequest(BaseModel):
    plan_code: Literal["api_monthly", "api_annual"] | None = None
    api_access_enabled: bool | None = None
    soft_limit_monthly: int | None = Field(default=None, ge=0, le=100_000_000)
    overage_enabled: bool | None = None
    overage_price_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    overage_unit_quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    reason: str = Field(min_length=8, max_length=500)
    step_up_password: str = Field(min_length=8, max_length=128)
    confirm_phrase: str = Field(min_length=3, max_length=32)

    @model_validator(mode="after")
    def _validate_has_any_mutation(self) -> "AdminApiPartnerEntitlementUpdateRequest":
        mutable_fields = {
            "plan_code",
            "api_access_enabled",
            "soft_limit_monthly",
            "overage_enabled",
            "overage_price_cents",
            "overage_unit_quantity",
        }
        if not (self.model_fields_set & mutable_fields):
            raise ValueError("At least one entitlement field must be provided")
        return self


class AdminApiPartnerEntitlementUpdateOut(BaseModel):
    action_id: UUID
    acted_at: datetime
    actor_user_id: UUID
    user_id: UUID
    email: str
    reason: str
    old_entitlement: AdminApiPartnerEntitlementOut
    new_entitlement: AdminApiPartnerEntitlementOut


class AdminAuditLogItemOut(BaseModel):
    id: UUID
    actor_user_id: UUID
    action_type: str
    target_type: str
    target_id: str | None
    reason: str
    before_payload: dict | None
    after_payload: dict | None
    request_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAuditLogListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminAuditLogItemOut]
