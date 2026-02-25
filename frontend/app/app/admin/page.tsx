"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import {
  cancelAdminUserBilling,
  getAdminAuditLogs,
  getAdminOverview,
  getAdminUserBilling,
  getAdminUsers,
  reactivateAdminUserBilling,
  resyncAdminUserBilling,
  requestAdminUserPasswordReset,
  updateAdminUserActive,
  updateAdminUserRole,
  updateAdminUserTier,
} from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import {
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
  const recentCycles = overview?.recent_cycles ?? [];
  const topSignalTypes = Object.entries(ops?.signals_created_by_type ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

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
          <p>4. Review immutable admin audit entries with action and target filters.</p>
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
                } else {
                  setBillingSummary(null);
                  setBillingError(null);
                }
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
            Most operational actions (deploy, backfill, partner key lifecycle) remain script-driven or protected
            internal endpoints.
          </p>
        </div>
      </div>
    </section>
  );
}
