"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import {
  cancelAdminUserBilling,
  downloadAdminOutcomesCsv,
  downloadAdminOutcomesJson,
  getAdminAuditLogs,
  getAdminOutcomesReport,
  getAdminOverview,
  getAdminUserApiPartnerEntitlement,
  getAdminUserApiPartnerKeys,
  getAdminUserBilling,
  getAdminUsers,
  issueAdminUserApiPartnerKey,
  revokeAdminUserApiPartnerKey,
  reactivateAdminUserBilling,
  rotateAdminUserApiPartnerKey,
  resyncAdminUserBilling,
  requestAdminUserPasswordReset,
  updateAdminUserApiPartnerEntitlement,
  updateAdminUserActive,
  updateAdminUserRole,
  updateAdminUserTier,
} from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import {
  AdminOutcomesReport,
  AdminApiPartnerEntitlement,
  AdminApiPartnerKeyList,
  AdminAuditLogList,
  AdminBillingOverview,
  AdminOverview,
  AdminRole,
  AdminUserSearchItem,
} from "@/lib/types";

export default function AdminPage() {
  const { user, loading, token } = useCurrentUser(true);
  const [days, setDays] = useState(7);
  const [cycleLimit, setCycleLimit] = useState(20);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [outcomes, setOutcomes] = useState<AdminOutcomesReport | null>(null);
  const [outcomesDays, setOutcomesDays] = useState(30);
  const [outcomesBaselineDays, setOutcomesBaselineDays] = useState(14);
  const [outcomesSportKey, setOutcomesSportKey] = useState<
    "" | "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl"
  >("");
  const [outcomesSignalType, setOutcomesSignalType] = useState("");
  const [outcomesMarket, setOutcomesMarket] = useState<"" | "spreads" | "totals" | "h2h">("");
  const [outcomesTimeBucket, setOutcomesTimeBucket] = useState<
    "" | "OPEN" | "MID" | "LATE" | "PRETIP" | "UNKNOWN"
  >("");
  const [outcomesLoading, setOutcomesLoading] = useState(false);
  const [outcomesError, setOutcomesError] = useState<string | null>(null);
  const [outcomesExportTable, setOutcomesExportTable] = useState<
    "summary" | "by_signal_type" | "by_market" | "top_filtered_reasons"
  >("summary");
  const [outcomesExporting, setOutcomesExporting] = useState<"json" | "csv" | null>(null);
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogList | null>(null);
  const [auditActionType, setAuditActionType] = useState("");
  const [auditTargetIdFilter, setAuditTargetIdFilter] = useState("");
  const [mutationUserId, setMutationUserId] = useState("");
  const [mutationReason, setMutationReason] = useState("");
  const [mutationTier, setMutationTier] = useState<"free" | "pro">("pro");
  const [mutationRole, setMutationRole] = useState<AdminRole | "none">("support_admin");
  const [mutationActive, setMutationActive] = useState<"active" | "inactive">("active");
  const [mutationStepUpPassword, setMutationStepUpPassword] = useState("");
  const [mutationConfirmPhrase, setMutationConfirmPhrase] = useState("");
  const [mutationLoading, setMutationLoading] = useState(false);
  const [mutationResult, setMutationResult] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [billingSummary, setBillingSummary] = useState<AdminBillingOverview | null>(null);
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);
  const [partnerKeysSummary, setPartnerKeysSummary] = useState<AdminApiPartnerKeyList | null>(null);
  const [partnerKeysLoading, setPartnerKeysLoading] = useState(false);
  const [partnerKeysError, setPartnerKeysError] = useState<string | null>(null);
  const [partnerEntitlement, setPartnerEntitlement] = useState<AdminApiPartnerEntitlement | null>(null);
  const [partnerEntitlementLoading, setPartnerEntitlementLoading] = useState(false);
  const [partnerEntitlementError, setPartnerEntitlementError] = useState<string | null>(null);
  const [partnerPlanCode, setPartnerPlanCode] = useState<"none" | "api_monthly" | "api_annual">("none");
  const [partnerAccessEnabled, setPartnerAccessEnabled] = useState<"enabled" | "disabled">("disabled");
  const [partnerSoftLimitMonthly, setPartnerSoftLimitMonthly] = useState("");
  const [partnerOverageEnabled, setPartnerOverageEnabled] = useState<"enabled" | "disabled">("enabled");
  const [partnerOveragePriceCents, setPartnerOveragePriceCents] = useState("");
  const [partnerOverageUnitQuantity, setPartnerOverageUnitQuantity] = useState("1000");
  const [partnerKeyName, setPartnerKeyName] = useState("Primary Partner Key");
  const [partnerKeyExpiresDays, setPartnerKeyExpiresDays] = useState("90");
  const [latestIssuedApiKey, setLatestIssuedApiKey] = useState<string | null>(null);
  const [userSearchQuery, setUserSearchQuery] = useState("");
  const [userSearchResults, setUserSearchResults] = useState<AdminUserSearchItem[]>([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);
  const [userSearchError, setUserSearchError] = useState<string | null>(null);

  const loadAudit = async (authToken: string) => {
    const payload = await getAdminAuditLogs(authToken, {
      limit: 20,
      offset: 0,
      action_type: auditActionType || undefined,
      target_id: auditTargetIdFilter || undefined,
    });
    setAuditLogs(payload);
  };

  const loadOutcomes = async (authToken: string) => {
    setOutcomesLoading(true);
    setOutcomesError(null);
    try {
      const payload = await getAdminOutcomesReport(authToken, {
        days: outcomesDays,
        baseline_days: outcomesBaselineDays,
        sport_key: outcomesSportKey || undefined,
        signal_type: outcomesSignalType.trim() || undefined,
        market: outcomesMarket || undefined,
        time_bucket: outcomesTimeBucket || undefined,
      });
      setOutcomes(payload);
    } catch (err) {
      setOutcomes(null);
      setOutcomesError(err instanceof Error ? err.message : "Failed to load outcomes report");
    } finally {
      setOutcomesLoading(false);
    }
  };

  const runOutcomesExportJson = async () => {
    if (!token) {
      return;
    }
    setOutcomesExporting("json");
    setOutcomesError(null);
    try {
      await downloadAdminOutcomesJson(token, {
        days: outcomesDays,
        baseline_days: outcomesBaselineDays,
        sport_key: outcomesSportKey || undefined,
        signal_type: outcomesSignalType.trim() || undefined,
        market: outcomesMarket || undefined,
        time_bucket: outcomesTimeBucket || undefined,
      });
    } catch (err) {
      setOutcomesError(err instanceof Error ? err.message : "Failed to export JSON report");
    } finally {
      setOutcomesExporting(null);
    }
  };

  const runOutcomesExportCsv = async () => {
    if (!token) {
      return;
    }
    setOutcomesExporting("csv");
    setOutcomesError(null);
    try {
      await downloadAdminOutcomesCsv(token, {
        table: outcomesExportTable,
        days: outcomesDays,
        baseline_days: outcomesBaselineDays,
        sport_key: outcomesSportKey || undefined,
        signal_type: outcomesSignalType.trim() || undefined,
        market: outcomesMarket || undefined,
        time_bucket: outcomesTimeBucket || undefined,
      });
    } catch (err) {
      setOutcomesError(err instanceof Error ? err.message : "Failed to export CSV report");
    } finally {
      setOutcomesExporting(null);
    }
  };

  const load = async () => {
    if (!token || !user?.is_admin) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const [overviewPayload] = await Promise.all([
        getAdminOverview(token, { days, cycle_limit: cycleLimit }),
        loadAudit(token),
      ]);
      setOverview(overviewPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setRefreshing(false);
    }
  };

  const loadBilling = async (authToken: string, userId: string) => {
    if (!authToken || !userId.trim()) {
      setBillingSummary(null);
      setBillingError(null);
      return;
    }
    setBillingLoading(true);
    setBillingError(null);
    try {
      const payload = await getAdminUserBilling(authToken, userId.trim());
      setBillingSummary(payload);
    } catch (err) {
      setBillingSummary(null);
      setBillingError(err instanceof Error ? err.message : "Failed to load billing state");
    } finally {
      setBillingLoading(false);
    }
  };

  const loadPartnerKeys = async (authToken: string, userId: string) => {
    if (!authToken || !userId.trim()) {
      setPartnerKeysSummary(null);
      setPartnerKeysError(null);
      return;
    }
    setPartnerKeysLoading(true);
    setPartnerKeysError(null);
    try {
      const payload = await getAdminUserApiPartnerKeys(authToken, userId.trim());
      setPartnerKeysSummary(payload);
    } catch (err) {
      setPartnerKeysSummary(null);
      setPartnerKeysError(err instanceof Error ? err.message : "Failed to load API partner keys");
    } finally {
      setPartnerKeysLoading(false);
    }
  };

  const loadPartnerEntitlement = async (authToken: string, userId: string) => {
    if (!authToken || !userId.trim()) {
      setPartnerEntitlement(null);
      setPartnerEntitlementError(null);
      return;
    }
    setPartnerEntitlementLoading(true);
    setPartnerEntitlementError(null);
    try {
      const payload = await getAdminUserApiPartnerEntitlement(authToken, userId.trim());
      setPartnerEntitlement(payload);
      setPartnerPlanCode(payload.plan_code ?? "none");
      setPartnerAccessEnabled(payload.api_access_enabled ? "enabled" : "disabled");
      setPartnerSoftLimitMonthly(
        payload.soft_limit_monthly != null ? String(payload.soft_limit_monthly) : "",
      );
      setPartnerOverageEnabled(payload.overage_enabled ? "enabled" : "disabled");
      setPartnerOveragePriceCents(
        payload.overage_price_cents != null ? String(payload.overage_price_cents) : "",
      );
      setPartnerOverageUnitQuantity(String(payload.overage_unit_quantity ?? 1000));
    } catch (err) {
      setPartnerEntitlement(null);
      setPartnerEntitlementError(
        err instanceof Error ? err.message : "Failed to load partner entitlement",
      );
    } finally {
      setPartnerEntitlementLoading(false);
    }
  };

  const canProceedMutation = (): boolean => {
    if (!token || !mutationUserId.trim()) {
      setMutationError("User ID is required.");
      return false;
    }
    if (mutationReason.trim().length < 8) {
      setMutationError("Reason must be at least 8 characters.");
      return false;
    }
    if (mutationStepUpPassword.trim().length < 8) {
      setMutationError("Step-up password is required.");
      return false;
    }
    if (mutationConfirmPhrase.trim().toUpperCase() !== "CONFIRM") {
      setMutationError("Type CONFIRM to proceed.");
      return false;
    }
    return true;
  };

  const runTierUpdate = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await updateAdminUserTier(token, mutationUserId.trim(), {
        tier: mutationTier,
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Tier updated: ${result.email} (${result.old_tier} -> ${result.new_tier}), action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Tier update failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runRoleUpdate = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await updateAdminUserRole(token, mutationUserId.trim(), {
        admin_role: mutationRole === "none" ? null : mutationRole,
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Role updated: ${result.email} (${result.old_admin_role ?? "none"} -> ${result.new_admin_role ?? "none"}), action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Role update failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runActiveUpdate = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await updateAdminUserActive(token, mutationUserId.trim(), {
        is_active: mutationActive === "active",
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Account status updated: ${result.email} (${result.old_is_active ? "active" : "inactive"} -> ${result.new_is_active ? "active" : "inactive"}), action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Account status update failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runPasswordResetRequest = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await requestAdminUserPasswordReset(token, mutationUserId.trim(), {
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      const tokenSuffix =
        result.reset_token && result.expires_in_minutes
          ? ` Reset token: ${result.reset_token} (expires in ${result.expires_in_minutes}m).`
          : "";
      setMutationResult(`Password reset initiated for ${result.email}, action ${result.action_id}.${tokenSuffix}`);
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Password reset request failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runBillingResync = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await resyncAdminUserBilling(token, mutationUserId.trim(), {
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Billing resync completed for ${result.email}, operation ${result.operation}, action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadBilling(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Billing resync failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runBillingCancel = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await cancelAdminUserBilling(token, mutationUserId.trim(), {
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Billing cancel scheduled for ${result.email}, action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadBilling(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Billing cancel failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runBillingReactivate = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await reactivateAdminUserBilling(token, mutationUserId.trim(), {
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Billing reactivated for ${result.email}, action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadBilling(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Billing reactivation failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const parseExpiresDays = (): number | undefined => {
    const parsed = Number(partnerKeyExpiresDays);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return undefined;
    }
    return Math.floor(parsed);
  };

  const runIssuePartnerKey = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    if (partnerKeyName.trim().length < 3) {
      setMutationError("API key name must be at least 3 characters.");
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await issueAdminUserApiPartnerKey(token, mutationUserId.trim(), {
        name: partnerKeyName.trim(),
        expires_in_days: parseExpiresDays(),
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setLatestIssuedApiKey(result.api_key);
      setMutationResult(`Issued API key '${result.key.name}' for ${result.email}, action ${result.action_id}`);
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadPartnerKeys(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "API key issue failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runRevokePartnerKey = async (keyId: string) => {
    if (!token || !canProceedMutation()) {
      return;
    }
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await revokeAdminUserApiPartnerKey(token, mutationUserId.trim(), keyId, {
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setMutationResult(
        `Revoked API key ${result.key_prefix} for ${result.email}, action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadPartnerKeys(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "API key revoke failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runRotatePartnerKey = async (keyId: string, fallbackName: string) => {
    if (!token || !canProceedMutation()) {
      return;
    }
    const nextName = partnerKeyName.trim() || fallbackName;
    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await rotateAdminUserApiPartnerKey(token, mutationUserId.trim(), keyId, {
        name: nextName,
        expires_in_days: parseExpiresDays(),
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setLatestIssuedApiKey(result.api_key);
      setMutationResult(
        `Rotated API key for ${result.email}. New key '${result.key.name}', action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadPartnerKeys(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "API key rotate failed");
    } finally {
      setMutationLoading(false);
    }
  };

  const runUpdatePartnerEntitlement = async () => {
    if (!token || !canProceedMutation()) {
      return;
    }
    const parsedSoftLimit =
      partnerSoftLimitMonthly.trim() === "" ? null : Number(partnerSoftLimitMonthly.trim());
    if (parsedSoftLimit != null && (!Number.isInteger(parsedSoftLimit) || parsedSoftLimit < 0)) {
      setMutationError("Soft limit monthly must be a non-negative whole number.");
      return;
    }

    const parsedOveragePrice =
      partnerOveragePriceCents.trim() === "" ? null : Number(partnerOveragePriceCents.trim());
    if (parsedOveragePrice != null && (!Number.isInteger(parsedOveragePrice) || parsedOveragePrice < 0)) {
      setMutationError("Overage price (cents) must be a non-negative whole number.");
      return;
    }

    const parsedOverageUnitQuantity = Number(partnerOverageUnitQuantity.trim());
    if (!Number.isInteger(parsedOverageUnitQuantity) || parsedOverageUnitQuantity <= 0) {
      setMutationError("Overage unit quantity must be a positive whole number.");
      return;
    }

    setMutationLoading(true);
    setMutationError(null);
    setMutationResult(null);
    try {
      const result = await updateAdminUserApiPartnerEntitlement(token, mutationUserId.trim(), {
        plan_code: partnerPlanCode === "none" ? null : partnerPlanCode,
        api_access_enabled: partnerAccessEnabled === "enabled",
        soft_limit_monthly: parsedSoftLimit,
        overage_enabled: partnerOverageEnabled === "enabled",
        overage_price_cents: parsedOveragePrice,
        overage_unit_quantity: parsedOverageUnitQuantity,
        reason: mutationReason.trim(),
        step_up_password: mutationStepUpPassword,
        confirm_phrase: mutationConfirmPhrase.trim(),
      });
      setPartnerEntitlement(result.new_entitlement);
      setMutationResult(
        `Partner entitlement updated for ${result.email}, action ${result.action_id}`,
      );
      setMutationStepUpPassword("");
      setMutationConfirmPhrase("");
      await loadPartnerEntitlement(token, mutationUserId.trim());
      await load();
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Partner entitlement update failed");
    } finally {
      setMutationLoading(false);
    }
  };

  useEffect(() => {
    if (!token || !user?.is_admin) {
      return;
    }
    const query = userSearchQuery.trim();
    if (query.length < 2) {
      setUserSearchResults([]);
      setUserSearchError(null);
      setUserSearchLoading(false);
      return;
    }

    let canceled = false;
    const timer = window.setTimeout(async () => {
      setUserSearchLoading(true);
      setUserSearchError(null);
      try {
        const payload = await getAdminUsers(token, { q: query, limit: 12 });
        if (!canceled) {
          setUserSearchResults(payload.items);
        }
      } catch (err) {
        if (!canceled) {
          setUserSearchResults([]);
          setUserSearchError(err instanceof Error ? err.message : "User search failed");
        }
      } finally {
        if (!canceled) {
          setUserSearchLoading(false);
        }
      }
    }, 250);

    return () => {
      canceled = true;
      window.clearTimeout(timer);
    };
  }, [token, user?.is_admin, userSearchQuery]);

  useEffect(() => {
    if (!loading && token && user?.is_admin) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, token, user?.is_admin, days, cycleLimit]);

  useEffect(() => {
    if (!loading && token && user?.is_admin) {
      void loadOutcomes(token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    loading,
    token,
    user?.is_admin,
    outcomesDays,
    outcomesBaselineDays,
    outcomesSportKey,
    outcomesSignalType,
    outcomesMarket,
    outcomesTimeBucket,
  ]);

  if (loading || !user) {
    return <LoadingState label="Loading admin panel..." />;
  }

  if (!user.is_admin) {
    return (
      <section className="space-y-3">
        <h1 className="text-xl font-semibold">Admin</h1>
        <div className="rounded-xl border border-borderTone bg-panel p-5 text-sm text-textMute shadow-terminal">
          <p className="text-textMain">Admin access is required for this page.</p>
          <p className="mt-2">
            Go back to{" "}
            <Link href="/app/dashboard" className="text-accent hover:underline">
              Dashboard
            </Link>
            .
          </p>
        </div>
      </section>
    );
  }

  const proAccess = hasProAccess(user);
  const report = overview?.report ?? null;
  const ops = report?.ops;
  const reliability = report?.reliability;
  const conversion = overview?.conversion ?? null;
  const outcomesReport = outcomes;
  const recentCycles = overview?.recent_cycles ?? [];
  const topSignalTypes = Object.entries(ops?.signals_created_by_type ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const formatRate = (value: number | null | undefined) =>
    `${((value ?? 0) * 100).toFixed(1)}%`;
  const formatDeltaRate = (value: number | null | undefined) =>
    `${(value ?? 0) >= 0 ? "+" : ""}${((value ?? 0) * 100).toFixed(1)} pp`;
  const formatSigned = (value: number | null | undefined, digits = 3) => {
    if (value == null) {
      return "-";
    }
    const next = Number(value);
    return `${next >= 0 ? "+" : ""}${next.toFixed(digits)}`;
  };

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-textMute">Current account role and operational access scope.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="text-xs text-textMute">
          Report Days
          <input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(event) => setDays(Math.max(1, Math.min(30, Number(event.target.value) || 7)))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Recent Cycles
          <input
            type="number"
            min={1}
            max={100}
            value={cycleLimit}
            onChange={(event) =>
              setCycleLimit(Math.max(1, Math.min(100, Number(event.target.value) || 20)))
            }
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <div className="md:col-span-2 flex items-end">
          <button
            onClick={() => {
              void load();
            }}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
          >
            {refreshing ? "Refreshing" : "Refresh Admin Data"}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Tier</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{user.tier}</p>
        </div>
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Pro Access</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{proAccess ? "Enabled" : "Disabled"}</p>
        </div>
        <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Admin Flag</p>
          <p className="mt-1 text-lg font-semibold text-textMain">{user.is_admin ? "Enabled" : "Disabled"}</p>
        </div>
      </div>

      {report && (
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Cycles</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{ops?.total_cycles ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">Degraded {ops?.degraded_cycles ?? 0}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Avg Cycle Duration</p>
            <p className="mt-1 text-lg font-semibold text-textMain">
              {ops?.avg_cycle_duration_ms != null
                ? `${Math.round(ops.avg_cycle_duration_ms)} ms`
                : "-"}
            </p>
            <p className="mt-1 text-xs text-textMute">Signals {ops?.total_signals_created ?? 0}</p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Alerts</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{reliability?.alerts_sent ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">
              Failed {reliability?.alerts_failed ?? 0} (
              {((reliability?.alert_failure_rate ?? 0) * 100).toFixed(1)}%)
            </p>
          </div>
          <div className="rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
            <p className="text-xs uppercase tracking-wider text-textMute">Requests Used</p>
            <p className="mt-1 text-lg font-semibold text-textMain">{ops?.total_requests_used ?? 0}</p>
            <p className="mt-1 text-xs text-textMute">
              Avg remaining{" "}
              {ops?.avg_requests_remaining != null ? ops.avg_requests_remaining.toFixed(1) : "-"}
            </p>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-textMute">Outcomes KPIs</p>
            <p className="mt-1 text-xs text-textMute">
              Outcome uses CLV-standard definition (positive when clv_line &gt; 0 or clv_prob &gt; 0).
            </p>
            <p className="text-xs text-textMute">
              This is prioritization/quality monitoring, not guaranteed betting outcomes.
            </p>
          </div>
          <button
            onClick={() => {
              if (token) {
                void loadOutcomes(token);
              }
            }}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
            disabled={outcomesLoading}
          >
            {outcomesLoading ? "Refreshing..." : "Refresh Outcomes"}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="text-xs text-textMute">
            Days
            <input
              type="number"
              min={7}
              max={90}
              value={outcomesDays}
              onChange={(event) => {
                setOutcomesDays(Math.max(7, Math.min(90, Number(event.target.value) || 30)));
              }}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Baseline Days
            <input
              type="number"
              min={7}
              max={30}
              value={outcomesBaselineDays}
              onChange={(event) => {
                setOutcomesBaselineDays(Math.max(7, Math.min(30, Number(event.target.value) || 14)));
              }}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Sport
            <select
              value={outcomesSportKey}
              onChange={(event) =>
                setOutcomesSportKey(
                  event.target.value as "" | "basketball_nba" | "basketball_ncaab" | "americanfootball_nfl",
                )
              }
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="">all</option>
              <option value="basketball_nba">NBA</option>
              <option value="basketball_ncaab">NCAAB</option>
              <option value="americanfootball_nfl">NFL</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Signal Type
            <input
              value={outcomesSignalType}
              onChange={(event) => setOutcomesSignalType(event.target.value)}
              placeholder="MOVE"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Market
            <select
              value={outcomesMarket}
              onChange={(event) => setOutcomesMarket(event.target.value as "" | "spreads" | "totals" | "h2h")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="">all</option>
              <option value="spreads">spreads</option>
              <option value="totals">totals</option>
              <option value="h2h">h2h</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Time Bucket
            <select
              value={outcomesTimeBucket}
              onChange={(event) =>
                setOutcomesTimeBucket(
                  event.target.value as "" | "OPEN" | "MID" | "LATE" | "PRETIP" | "UNKNOWN",
                )
              }
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="">all</option>
              <option value="OPEN">OPEN</option>
              <option value="MID">MID</option>
              <option value="LATE">LATE</option>
              <option value="PRETIP">PRETIP</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-xs text-textMute">
            CSV Table
            <select
              value={outcomesExportTable}
              onChange={(event) =>
                setOutcomesExportTable(
                  event.target.value as
                    | "summary"
                    | "by_signal_type"
                    | "by_market"
                    | "top_filtered_reasons",
                )
              }
              className="mt-1 rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="summary">summary</option>
              <option value="by_signal_type">by_signal_type</option>
              <option value="by_market">by_market</option>
              <option value="top_filtered_reasons">top_filtered_reasons</option>
            </select>
          </label>
          <button
            onClick={() => {
              void runOutcomesExportJson();
            }}
            disabled={outcomesExporting !== null}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {outcomesExporting === "json" ? "Exporting..." : "Export JSON"}
          </button>
          <button
            onClick={() => {
              void runOutcomesExportCsv();
            }}
            disabled={outcomesExporting !== null}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {outcomesExporting === "csv" ? "Exporting..." : "Export CSV"}
          </button>
        </div>

        {outcomesError && <p className="mt-3 text-sm text-negative">{outcomesError}</p>}
        {outcomesLoading && !outcomesReport && <p className="mt-3 text-sm text-textMute">Loading outcomes...</p>}

        {outcomesReport && (
          <>
            <div className="mt-4 grid gap-3 md:grid-cols-5">
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Status</p>
                <p className="mt-1 text-sm font-semibold text-textMain">{outcomesReport.status}</p>
                <p className="mt-1 text-[11px] text-textMute">{outcomesReport.status_reason}</p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">CLV Positive Rate</p>
                <p className="mt-1 text-sm font-semibold text-textMain">
                  {formatRate(outcomesReport.kpis.clv_positive_rate)}
                </p>
                <p className="mt-1 text-[11px] text-textMute">
                  Δ {formatDeltaRate(outcomesReport.delta_vs_baseline.clv_positive_rate_delta)}
                </p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">CLV Samples</p>
                <p className="mt-1 text-sm font-semibold text-textMain">{outcomesReport.kpis.clv_samples}</p>
                <p className="mt-1 text-[11px] text-textMute">
                  +{outcomesReport.kpis.positive_count} / -{outcomesReport.kpis.negative_count}
                </p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Avg CLV</p>
                <p className="mt-1 text-sm font-semibold text-textMain">
                  line {formatSigned(outcomesReport.kpis.avg_clv_line)}
                </p>
                <p className="mt-1 text-[11px] text-textMute">
                  prob {formatSigned(outcomesReport.kpis.avg_clv_prob)}
                </p>
              </div>
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Reliability</p>
                <p className="mt-1 text-sm font-semibold text-textMain">
                  Sent {formatRate(outcomesReport.kpis.sent_rate)} / Stale {formatRate(outcomesReport.kpis.stale_rate)}
                </p>
                <p className="mt-1 text-[11px] text-textMute">
                  Degraded {formatRate(outcomesReport.kpis.degraded_cycle_rate)} • Alert fail {formatRate(outcomesReport.kpis.alert_failure_rate)}
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">By Signal Type</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Signal</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                        <th className="border-b border-borderTone py-1.5">%+</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.by_signal_type.map((row) => (
                        <tr key={`signal-${row.name}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.name}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{formatRate(row.positive_rate)}</td>
                        </tr>
                      ))}
                      {outcomesReport.by_signal_type.length === 0 && (
                        <tr>
                          <td colSpan={3} className="py-2 text-textMute">
                            No rows for current filter set.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">By Market</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Market</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                        <th className="border-b border-borderTone py-1.5">%+</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.by_market.map((row) => (
                        <tr key={`market-${row.name}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.name}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{formatRate(row.positive_rate)}</td>
                        </tr>
                      ))}
                      {outcomesReport.by_market.length === 0 && (
                        <tr>
                          <td colSpan={3} className="py-2 text-textMute">
                            No rows for current filter set.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded border border-borderTone bg-panelSoft p-3">
                <p className="text-[11px] uppercase tracking-wider text-textMute">Top Filtered Reasons</p>
                <div className="mt-2 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left uppercase tracking-wider text-textMute">
                        <th className="border-b border-borderTone py-1.5">Reason</th>
                        <th className="border-b border-borderTone py-1.5">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomesReport.top_filtered_reasons.map((row) => (
                        <tr key={`reason-${row.reason}`}>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.reason}</td>
                          <td className="border-b border-borderTone/50 py-1.5 text-textMain">{row.count}</td>
                        </tr>
                      ))}
                      {outcomesReport.top_filtered_reasons.length === 0 && (
                        <tr>
                          <td colSpan={2} className="py-2 text-textMute">
                            No filtered reasons in this window.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {report && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Top Signal Types (Window)</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {topSignalTypes.length === 0 && <span className="text-sm text-textMute">No signal data in window.</span>}
            {topSignalTypes.map(([signalType, count]) => (
              <span
                key={signalType}
                className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-xs text-textMain"
              >
                {signalType}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {conversion && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="text-xs uppercase tracking-wider text-textMute">Conversion Funnel (Free Teaser)</p>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Teaser Views</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{conversion.teaser_views}</p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Upgrade Clicks</p>
              <p className="mt-1 text-lg font-semibold text-textMain">{conversion.teaser_clicks}</p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">CTR</p>
              <p className="mt-1 text-lg font-semibold text-textMain">
                {(conversion.click_through_rate * 100).toFixed(1)}%
              </p>
            </div>
            <div className="rounded border border-borderTone bg-panelSoft p-3">
              <p className="text-[11px] uppercase tracking-wider text-textMute">Unique Users</p>
              <p className="mt-1 text-lg font-semibold text-textMain">
                {conversion.unique_viewers} / {conversion.unique_clickers}
              </p>
              <p className="mt-1 text-xs text-textMute">viewers / clickers</p>
            </div>
          </div>

          <div className="mt-4 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Sport</th>
                  <th className="border-b border-borderTone py-2">Views</th>
                  <th className="border-b border-borderTone py-2">Clicks</th>
                  <th className="border-b border-borderTone py-2">CTR</th>
                </tr>
              </thead>
              <tbody>
                {conversion.by_sport.map((row) => (
                  <tr key={`conv-${row.sport_key}`}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.sport_key}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.teaser_views}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{row.teaser_clicks}</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {(row.click_through_rate * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
                {conversion.by_sport.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-3 text-xs text-textMute">
                      No teaser interactions recorded in this window.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {overview && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <p className="mb-3 text-xs uppercase tracking-wider text-textMute">Recent Poll Cycles</p>
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                  <th className="border-b border-borderTone py-2">Started</th>
                  <th className="border-b border-borderTone py-2">Duration</th>
                  <th className="border-b border-borderTone py-2">Snapshots</th>
                  <th className="border-b border-borderTone py-2">Signals</th>
                  <th className="border-b border-borderTone py-2">Alerts Failed</th>
                  <th className="border-b border-borderTone py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentCycles.map((cycle) => (
                  <tr key={cycle.id}>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {new Date(cycle.started_at).toLocaleString([], {
                        month: "short",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.duration_ms} ms</td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {cycle.snapshots_inserted ?? 0}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">
                      {cycle.signals_created_total ?? 0}
                    </td>
                    <td className="border-b border-borderTone/50 py-2 text-textMain">{cycle.alerts_failed ?? 0}</td>
                    <td className="border-b border-borderTone/50 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs uppercase tracking-wider ${
                          cycle.degraded ? "bg-negative/10 text-negative" : "bg-positive/10 text-positive"
                        }`}
                      >
                        {cycle.degraded ? "degraded" : "ok"}
                      </span>
                    </td>
                  </tr>
                ))}
                {recentCycles.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-3 text-xs text-textMute">
                      No recent cycles in selected window.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">What Admin Can Do Today</p>
        <div className="mt-3 space-y-2 text-sm text-textMain">
          <p>1. Access all Pro-gated product surfaces and real-time feeds.</p>
          <p>2. Update user tier, role, and account status with reason + step-up confirmation.</p>
          <p>3. Manage billing state (resync, cancel, reactivate) with auditable controls.</p>
          <p>4. Set API partner entitlement controls (plan, access, soft limit, overage policy).</p>
          <p>5. Issue, rotate, and revoke API partner keys for selected users.</p>
          <p>6. Review immutable admin audit entries with action and target filters.</p>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">User Access Actions</p>
        <p className="mt-2 text-xs text-textMute">
          Changes require a reason, step-up password, and typed confirmation. All actions are recorded in immutable admin audit logs.
        </p>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-xs text-textMute">
            Find User (Email or UUID)
            <input
              value={userSearchQuery}
              onChange={(event) => setUserSearchQuery(event.target.value)}
              placeholder="search@example.com or uuid"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
            <p className="mt-1 text-[11px] text-textMute">
              {userSearchLoading
                ? "Searching..."
                : userSearchQuery.trim().length < 2
                  ? "Enter at least 2 characters."
                  : `${userSearchResults.length} match(es)`}
            </p>
            {userSearchError && <p className="mt-1 text-[11px] text-negative">{userSearchError}</p>}
          </label>
          <label className="text-xs text-textMute">
            Search Results
            <select
              value={mutationUserId}
              onChange={(event) => {
                const nextUserId = event.target.value;
                setMutationUserId(nextUserId);
                setMutationError(null);
                if (token && nextUserId) {
                  void loadBilling(token, nextUserId);
                  void loadPartnerKeys(token, nextUserId);
                  void loadPartnerEntitlement(token, nextUserId);
                } else {
                  setBillingSummary(null);
                  setBillingError(null);
                  setPartnerKeysSummary(null);
                  setPartnerKeysError(null);
                  setPartnerEntitlement(null);
                  setPartnerEntitlementError(null);
                }
                setLatestIssuedApiKey(null);
                const selected = userSearchResults.find((item) => item.id === nextUserId);
                if (selected) {
                  setUserSearchQuery(selected.email);
                  setMutationTier(selected.tier === "pro" ? "pro" : "free");
                  setMutationRole(
                    selected.admin_role ?? (selected.is_admin ? "super_admin" : "none"),
                  );
                  setMutationActive(selected.is_active ? "active" : "inactive");
                }
              }}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="">Select user</option>
              {userSearchResults.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.email} • tier:{candidate.tier} • role:
                  {candidate.admin_role ?? (candidate.is_admin ? "super_admin" : "none")} • status:
                  {candidate.is_active ? "active" : "inactive"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-textMute">
            Target User ID (auto-filled)
            <input
              value={mutationUserId}
              onChange={(event) => {
                setMutationUserId(event.target.value);
                setBillingSummary(null);
                setBillingError(null);
                setPartnerKeysSummary(null);
                setPartnerKeysError(null);
                setPartnerEntitlement(null);
                setPartnerEntitlementError(null);
                setLatestIssuedApiKey(null);
              }}
              placeholder="uuid"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Audit Reason
            <input
              value={mutationReason}
              onChange={(event) => setMutationReason(event.target.value)}
              placeholder="Explain why this action is needed"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Step-up Password (Your Password)
            <input
              type="password"
              autoComplete="current-password"
              value={mutationStepUpPassword}
              onChange={(event) => setMutationStepUpPassword(event.target.value)}
              placeholder="Enter your current password"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Type CONFIRM
            <input
              value={mutationConfirmPhrase}
              onChange={(event) => setMutationConfirmPhrase(event.target.value)}
              placeholder="CONFIRM"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Tier
            <select
              value={mutationTier}
              onChange={(event) => setMutationTier(event.target.value as "free" | "pro")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="free">free</option>
              <option value="pro">pro</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Admin Role
            <select
              value={mutationRole}
              onChange={(event) => setMutationRole(event.target.value as AdminRole | "none")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="none">none</option>
              <option value="super_admin">super_admin</option>
              <option value="ops_admin">ops_admin</option>
              <option value="support_admin">support_admin</option>
              <option value="billing_admin">billing_admin</option>
            </select>
          </label>
          <label className="text-xs text-textMute">
            Account Status
            <select
              value={mutationActive}
              onChange={(event) => setMutationActive(event.target.value as "active" | "inactive")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>
        </div>

        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">Billing Snapshot</p>
            <button
              onClick={() => {
                if (token && mutationUserId.trim()) {
                  void loadBilling(token, mutationUserId.trim());
                }
              }}
              disabled={billingLoading || !mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {billingLoading ? "Loading..." : "Refresh Billing"}
            </button>
          </div>
          {billingError && <p className="mt-2 text-negative">{billingError}</p>}
          {!billingError && (
            <div className="mt-2 space-y-1">
              <p>
                Customer: <span className="text-textMain">{billingSummary?.stripe_customer_id ?? "-"}</span>
              </p>
              <p>
                Subscription ID:{" "}
                <span className="text-textMain">
                  {billingSummary?.subscription?.stripe_subscription_id ?? "-"}
                </span>
              </p>
              <p>
                Status: <span className="text-textMain">{billingSummary?.subscription?.status ?? "-"}</span>
                {" • "}Cancel at period end:{" "}
                <span className="text-textMain">
                  {billingSummary?.subscription
                    ? billingSummary.subscription.cancel_at_period_end
                      ? "yes"
                      : "no"
                    : "-"}
                </span>
              </p>
            </div>
          )}
        </div>

        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">API Partner Keys</p>
            <button
              onClick={() => {
                if (token && mutationUserId.trim()) {
                  void loadPartnerKeys(token, mutationUserId.trim());
                }
              }}
              disabled={partnerKeysLoading || !mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {partnerKeysLoading ? "Loading..." : "Refresh Keys"}
            </button>
          </div>
          {partnerKeysError && <p className="mt-2 text-negative">{partnerKeysError}</p>}
          {!partnerKeysError && (
            <>
              <div className="mt-2 flex flex-wrap gap-3">
                <p>
                  Total: <span className="text-textMain">{partnerKeysSummary?.total_keys ?? 0}</span>
                </p>
                <p>
                  Active: <span className="text-textMain">{partnerKeysSummary?.active_keys ?? 0}</span>
                </p>
                <p>
                  Used 30d: <span className="text-textMain">{partnerKeysSummary?.recently_used_30d ?? 0}</span>
                </p>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <label className="text-[11px] text-textMute">
                  Key Name
                  <input
                    value={partnerKeyName}
                    onChange={(event) => setPartnerKeyName(event.target.value)}
                    placeholder="Primary Partner Key"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
                <label className="text-[11px] text-textMute">
                  Expires in Days (optional)
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    value={partnerKeyExpiresDays}
                    onChange={(event) => setPartnerKeyExpiresDays(event.target.value)}
                    placeholder="90"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
              </div>
              {latestIssuedApiKey && (
                <div className="mt-3 rounded border border-accent/40 bg-accent/5 p-2">
                  <p className="text-[11px] uppercase tracking-wider text-accent">New API Key (shown once)</p>
                  <p className="mt-1 break-all font-mono text-[11px] text-textMain">{latestIssuedApiKey}</p>
                </div>
              )}
              <div className="mt-3 overflow-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead>
                    <tr className="text-left uppercase tracking-wider text-textMute">
                      <th className="border-b border-borderTone py-1.5">Prefix</th>
                      <th className="border-b border-borderTone py-1.5">Name</th>
                      <th className="border-b border-borderTone py-1.5">Status</th>
                      <th className="border-b border-borderTone py-1.5">Expires</th>
                      <th className="border-b border-borderTone py-1.5">Last Used</th>
                      <th className="border-b border-borderTone py-1.5">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(partnerKeysSummary?.items ?? []).map((keyRow) => (
                      <tr key={keyRow.id}>
                        <td className="border-b border-borderTone/50 py-1.5 font-mono text-textMain">{keyRow.key_prefix}</td>
                        <td className="border-b border-borderTone/50 py-1.5 text-textMain">{keyRow.name}</td>
                        <td className="border-b border-borderTone/50 py-1.5 text-textMain">
                          {keyRow.is_active ? "active" : "revoked"}
                        </td>
                        <td className="border-b border-borderTone/50 py-1.5 text-textMain">
                          {keyRow.expires_at
                            ? new Date(keyRow.expires_at).toLocaleDateString()
                            : "-"}
                        </td>
                        <td className="border-b border-borderTone/50 py-1.5 text-textMain">
                          {keyRow.last_used_at
                            ? new Date(keyRow.last_used_at).toLocaleString()
                            : "-"}
                        </td>
                        <td className="border-b border-borderTone/50 py-1.5">
                          <div className="flex flex-wrap gap-1">
                            <button
                              onClick={() => {
                                void runRotatePartnerKey(keyRow.id, keyRow.name);
                              }}
                              disabled={mutationLoading || !keyRow.is_active}
                              className="rounded border border-borderTone px-2 py-0.5 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
                            >
                              Rotate
                            </button>
                            <button
                              onClick={() => {
                                void runRevokePartnerKey(keyRow.id);
                              }}
                              disabled={mutationLoading || !keyRow.is_active}
                              className="rounded border border-borderTone px-2 py-0.5 text-[10px] uppercase tracking-wider text-textMute transition hover:border-negative hover:text-negative disabled:opacity-60"
                            >
                              Revoke
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {(partnerKeysSummary?.items.length ?? 0) === 0 && (
                      <tr>
                        <td colSpan={6} className="py-2 text-textMute">
                          No API partner keys for this user yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">API Partner Entitlement</p>
            <button
              onClick={() => {
                if (token && mutationUserId.trim()) {
                  void loadPartnerEntitlement(token, mutationUserId.trim());
                }
              }}
              disabled={partnerEntitlementLoading || !mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {partnerEntitlementLoading ? "Loading..." : "Refresh Entitlement"}
            </button>
          </div>
          {partnerEntitlementError && <p className="mt-2 text-negative">{partnerEntitlementError}</p>}
          {!partnerEntitlementError && (
            <>
              <div className="mt-2 flex flex-wrap gap-3">
                <p>
                  Access:{" "}
                  <span className="text-textMain">
                    {partnerEntitlement?.api_access_enabled ? "enabled" : "disabled"}
                  </span>
                </p>
                <p>
                  Plan: <span className="text-textMain">{partnerEntitlement?.plan_code ?? "-"}</span>
                </p>
                <p>
                  Updated:{" "}
                  <span className="text-textMain">
                    {partnerEntitlement?.updated_at
                      ? new Date(partnerEntitlement.updated_at).toLocaleString()
                      : "-"}
                  </span>
                </p>
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-3">
                <label className="text-[11px] text-textMute">
                  Plan
                  <select
                    value={partnerPlanCode}
                    onChange={(event) =>
                      setPartnerPlanCode(event.target.value as "none" | "api_monthly" | "api_annual")
                    }
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  >
                    <option value="none">none</option>
                    <option value="api_monthly">api_monthly</option>
                    <option value="api_annual">api_annual</option>
                  </select>
                </label>
                <label className="text-[11px] text-textMute">
                  API Access
                  <select
                    value={partnerAccessEnabled}
                    onChange={(event) => setPartnerAccessEnabled(event.target.value as "enabled" | "disabled")}
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  >
                    <option value="enabled">enabled</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
                <label className="text-[11px] text-textMute">
                  Soft Limit (monthly requests)
                  <input
                    type="number"
                    min={0}
                    value={partnerSoftLimitMonthly}
                    onChange={(event) => setPartnerSoftLimitMonthly(event.target.value)}
                    placeholder="leave blank to unset"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
                <label className="text-[11px] text-textMute">
                  Overage
                  <select
                    value={partnerOverageEnabled}
                    onChange={(event) => setPartnerOverageEnabled(event.target.value as "enabled" | "disabled")}
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  >
                    <option value="enabled">enabled</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
                <label className="text-[11px] text-textMute">
                  Overage Price (cents per unit)
                  <input
                    type="number"
                    min={0}
                    value={partnerOveragePriceCents}
                    onChange={(event) => setPartnerOveragePriceCents(event.target.value)}
                    placeholder="leave blank to unset"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
                <label className="text-[11px] text-textMute">
                  Overage Unit Quantity
                  <input
                    type="number"
                    min={1}
                    value={partnerOverageUnitQuantity}
                    onChange={(event) => setPartnerOverageUnitQuantity(event.target.value)}
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
              </div>
            </>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => {
              void runTierUpdate();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Update Tier"}
          </button>
          <button
            onClick={() => {
              void runRoleUpdate();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Update Role"}
          </button>
          <button
            onClick={() => {
              void runActiveUpdate();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Update Status"}
          </button>
          <button
            onClick={() => {
              void runPasswordResetRequest();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Initiate Password Reset"}
          </button>
          <button
            onClick={() => {
              void runBillingResync();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Resync Billing"}
          </button>
          <button
            onClick={() => {
              void runBillingCancel();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Cancel Subscription"}
          </button>
          <button
            onClick={() => {
              void runBillingReactivate();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Reactivate Subscription"}
          </button>
          <button
            onClick={() => {
              void runIssuePartnerKey();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Issue API Key"}
          </button>
          <button
            onClick={() => {
              void runUpdatePartnerEntitlement();
            }}
            disabled={mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {mutationLoading ? "Working..." : "Save API Entitlement"}
          </button>
        </div>
        {mutationError && <p className="mt-2 text-sm text-negative">{mutationError}</p>}
        {mutationResult && <p className="mt-2 text-sm text-positive">{mutationResult}</p>}
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-textMute">Admin Audit Log</p>
            <p className="mt-1 text-xs text-textMute">Newest entries first. Use filters to narrow results.</p>
          </div>
          <button
            onClick={() => {
              if (token) {
                void loadAudit(token);
              }
            }}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
          >
            Refresh Audit
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-xs text-textMute">
            Action Type Filter
            <input
              value={auditActionType}
              onChange={(event) => setAuditActionType(event.target.value)}
              placeholder="admin.user.role.update"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Target ID Filter
            <input
              value={auditTargetIdFilter}
              onChange={(event) => setAuditTargetIdFilter(event.target.value)}
              placeholder="target user uuid"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
        </div>

        <div className="mt-4 overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                <th className="border-b border-borderTone py-2">Created</th>
                <th className="border-b border-borderTone py-2">Action</th>
                <th className="border-b border-borderTone py-2">Target</th>
                <th className="border-b border-borderTone py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {(auditLogs?.items ?? []).map((row) => (
                <tr key={row.id}>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.action_type}</div>
                    <div className="text-xs text-textMute">actor {row.actor_user_id}</div>
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.target_type}</div>
                    <div className="text-xs text-textMute">{row.target_id ?? "-"}</div>
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.reason}</div>
                    {row.request_id && <div className="text-xs text-textMute">req {row.request_id}</div>}
                  </td>
                </tr>
              ))}
              {(auditLogs?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={4} className="py-3 text-xs text-textMute">
                    No audit events match current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">Important Notes</p>
        <div className="mt-3 space-y-2 text-sm text-textMute">
          <p>Admin UI currently focuses on access control mutations and audit visibility.</p>
          <p>Role changes require super-admin permission; tier updates allow broader admin roles.</p>
          <p>
            Most operational actions (deploy, deep backfills, and ops break-glass flows) remain script-driven or
            protected internal endpoints.
          </p>
        </div>
      </div>
    </section>
  );
}
