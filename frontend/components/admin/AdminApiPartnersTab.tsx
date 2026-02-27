"use client";

import { useState } from "react";

import {
  issueAdminUserApiPartnerKey,
  revokeAdminUserApiPartnerKey,
  rotateAdminUserApiPartnerKey,
  updateAdminUserApiPartnerEntitlement,
} from "@/lib/api";
import { useAdminContext } from "./AdminContext";
import { AdminUserSearch } from "./AdminUserSearch";
import { AdminMutationControls } from "./AdminMutationControls";

export function AdminApiPartnersTab() {
  const ctx = useAdminContext();

  const [partnerKeyName, setPartnerKeyName] = useState("Primary Partner Key");
  const [partnerKeyExpiresDays, setPartnerKeyExpiresDays] = useState("90");
  const [partnerPlanCode, setPartnerPlanCode] = useState<"none" | "api_monthly" | "api_annual">("none");
  const [partnerAccessEnabled, setPartnerAccessEnabled] = useState<"enabled" | "disabled">("disabled");
  const [partnerSoftLimitMonthly, setPartnerSoftLimitMonthly] = useState("");
  const [partnerOverageEnabled, setPartnerOverageEnabled] = useState<"enabled" | "disabled">("enabled");
  const [partnerOveragePriceCents, setPartnerOveragePriceCents] = useState("");
  const [partnerOverageUnitQuantity, setPartnerOverageUnitQuantity] = useState("1000");

  // Sync entitlement form when partner entitlement data loads
  const [trackedEntitlement, setTrackedEntitlement] = useState(ctx.partnerEntitlement);
  if (ctx.partnerEntitlement !== trackedEntitlement) {
    setTrackedEntitlement(ctx.partnerEntitlement);
    if (ctx.partnerEntitlement) {
      setPartnerPlanCode(ctx.partnerEntitlement.plan_code ?? "none");
      setPartnerAccessEnabled(ctx.partnerEntitlement.api_access_enabled ? "enabled" : "disabled");
      setPartnerSoftLimitMonthly(
        ctx.partnerEntitlement.soft_limit_monthly != null
          ? String(ctx.partnerEntitlement.soft_limit_monthly)
          : "",
      );
      setPartnerOverageEnabled(ctx.partnerEntitlement.overage_enabled ? "enabled" : "disabled");
      setPartnerOveragePriceCents(
        ctx.partnerEntitlement.overage_price_cents != null
          ? String(ctx.partnerEntitlement.overage_price_cents)
          : "",
      );
      setPartnerOverageUnitQuantity(String(ctx.partnerEntitlement.overage_unit_quantity ?? 1000));
    }
  }

  const parseExpiresDays = (): number | undefined => {
    const parsed = Number(partnerKeyExpiresDays);
    if (!Number.isFinite(parsed) || parsed <= 0) return undefined;
    return Math.floor(parsed);
  };

  const runIssuePartnerKey = async () => {
    if (partnerKeyName.trim().length < 3) {
      return;
    }
    await ctx.executeMutation(async () => {
      const result = await issueAdminUserApiPartnerKey(ctx.token, ctx.mutationUserId.trim(), {
        name: partnerKeyName.trim(),
        expires_in_days: parseExpiresDays(),
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.setLatestIssuedApiKey(result.api_key);
      ctx.refreshPartnerKeys();
      return `Issued API key '${result.key.name}' for ${result.email}, action ${result.action_id}`;
    });
  };

  const runRevokePartnerKey = async (keyId: string) => {
    await ctx.executeMutation(async () => {
      const result = await revokeAdminUserApiPartnerKey(ctx.token, ctx.mutationUserId.trim(), keyId, {
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.refreshPartnerKeys();
      return `Revoked API key ${result.key_prefix} for ${result.email}, action ${result.action_id}`;
    });
  };

  const runRotatePartnerKey = async (keyId: string, fallbackName: string) => {
    const nextName = partnerKeyName.trim() || fallbackName;
    await ctx.executeMutation(async () => {
      const result = await rotateAdminUserApiPartnerKey(ctx.token, ctx.mutationUserId.trim(), keyId, {
        name: nextName,
        expires_in_days: parseExpiresDays(),
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.setLatestIssuedApiKey(result.api_key);
      ctx.refreshPartnerKeys();
      return `Rotated API key for ${result.email}. New key '${result.key.name}', action ${result.action_id}`;
    });
  };

  const runUpdatePartnerEntitlement = async () => {
    const parsedSoftLimit =
      partnerSoftLimitMonthly.trim() === "" ? null : Number(partnerSoftLimitMonthly.trim());
    if (parsedSoftLimit != null && (!Number.isInteger(parsedSoftLimit) || parsedSoftLimit < 0)) {
      return;
    }
    const parsedOveragePrice =
      partnerOveragePriceCents.trim() === "" ? null : Number(partnerOveragePriceCents.trim());
    if (parsedOveragePrice != null && (!Number.isInteger(parsedOveragePrice) || parsedOveragePrice < 0)) {
      return;
    }
    const parsedOverageUnitQuantity = Number(partnerOverageUnitQuantity.trim());
    if (!Number.isInteger(parsedOverageUnitQuantity) || parsedOverageUnitQuantity <= 0) {
      return;
    }

    await ctx.executeMutation(async () => {
      const result = await updateAdminUserApiPartnerEntitlement(ctx.token, ctx.mutationUserId.trim(), {
        plan_code: partnerPlanCode === "none" ? null : partnerPlanCode,
        api_access_enabled: partnerAccessEnabled === "enabled",
        soft_limit_monthly: parsedSoftLimit,
        overage_enabled: partnerOverageEnabled === "enabled",
        overage_price_cents: parsedOveragePrice,
        overage_unit_quantity: parsedOverageUnitQuantity,
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.setPartnerEntitlement(result.new_entitlement);
      ctx.refreshPartnerEntitlement();
      return `Partner entitlement updated for ${result.email}, action ${result.action_id}`;
    });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">API Partner Management</p>
        <p className="mt-2 text-xs text-textMute">
          Issue, rotate, and revoke API partner keys. Manage entitlement plans and limits.
        </p>

        <div className="mt-4">
          <AdminUserSearch />
        </div>

        <AdminMutationControls />

        {/* API Partner Keys */}
        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">API Partner Keys</p>
            <button
              onClick={() => ctx.refreshPartnerKeys()}
              disabled={ctx.partnerKeysLoading || !ctx.mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {ctx.partnerKeysLoading ? "Loading..." : "Refresh Keys"}
            </button>
          </div>
          {ctx.partnerKeysError && <p className="mt-2 text-negative">{ctx.partnerKeysError}</p>}
          {!ctx.partnerKeysError && (
            <>
              <div className="mt-2 flex flex-wrap gap-3">
                <p>
                  Total: <span className="text-textMain">{ctx.partnerKeysSummary?.total_keys ?? 0}</span>
                </p>
                <p>
                  Active: <span className="text-textMain">{ctx.partnerKeysSummary?.active_keys ?? 0}</span>
                </p>
                <p>
                  Used 30d:{" "}
                  <span className="text-textMain">{ctx.partnerKeysSummary?.recently_used_30d ?? 0}</span>
                </p>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <label className="text-[11px] text-textMute">
                  Key Name
                  <input
                    value={partnerKeyName}
                    onChange={(e) => setPartnerKeyName(e.target.value)}
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
                    onChange={(e) => setPartnerKeyExpiresDays(e.target.value)}
                    placeholder="90"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
              </div>
              {ctx.latestIssuedApiKey && (
                <div className="mt-3 rounded border border-accent/40 bg-accent/5 p-2">
                  <p className="text-[11px] uppercase tracking-wider text-accent">
                    New API Key (shown once)
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-textMain">
                    {ctx.latestIssuedApiKey}
                  </p>
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
                    {(ctx.partnerKeysSummary?.items ?? []).map((keyRow) => (
                      <tr key={keyRow.id}>
                        <td className="border-b border-borderTone/50 py-1.5 font-mono text-textMain">
                          {keyRow.key_prefix}
                        </td>
                        <td className="border-b border-borderTone/50 py-1.5 text-textMain">
                          {keyRow.name}
                        </td>
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
                              onClick={() => void runRotatePartnerKey(keyRow.id, keyRow.name)}
                              disabled={ctx.mutationLoading || !keyRow.is_active}
                              className="rounded border border-borderTone px-2 py-0.5 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
                            >
                              Rotate
                            </button>
                            <button
                              onClick={() => void runRevokePartnerKey(keyRow.id)}
                              disabled={ctx.mutationLoading || !keyRow.is_active}
                              className="rounded border border-borderTone px-2 py-0.5 text-[10px] uppercase tracking-wider text-textMute transition hover:border-negative hover:text-negative disabled:opacity-60"
                            >
                              Revoke
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {(ctx.partnerKeysSummary?.items.length ?? 0) === 0 && (
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

        {/* API Partner Entitlement */}
        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">API Partner Entitlement</p>
            <button
              onClick={() => ctx.refreshPartnerEntitlement()}
              disabled={ctx.partnerEntitlementLoading || !ctx.mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {ctx.partnerEntitlementLoading ? "Loading..." : "Refresh Entitlement"}
            </button>
          </div>
          {ctx.partnerEntitlementError && (
            <p className="mt-2 text-negative">{ctx.partnerEntitlementError}</p>
          )}
          {!ctx.partnerEntitlementError && (
            <>
              <div className="mt-2 flex flex-wrap gap-3">
                <p>
                  Access:{" "}
                  <span className="text-textMain">
                    {ctx.partnerEntitlement?.api_access_enabled ? "enabled" : "disabled"}
                  </span>
                </p>
                <p>
                  Plan:{" "}
                  <span className="text-textMain">{ctx.partnerEntitlement?.plan_code ?? "-"}</span>
                </p>
                <p>
                  Updated:{" "}
                  <span className="text-textMain">
                    {ctx.partnerEntitlement?.updated_at
                      ? new Date(ctx.partnerEntitlement.updated_at).toLocaleString()
                      : "-"}
                  </span>
                </p>
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-3">
                <label className="text-[11px] text-textMute">
                  Plan
                  <select
                    value={partnerPlanCode}
                    onChange={(e) =>
                      setPartnerPlanCode(e.target.value as "none" | "api_monthly" | "api_annual")
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
                    onChange={(e) =>
                      setPartnerAccessEnabled(e.target.value as "enabled" | "disabled")
                    }
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
                    onChange={(e) => setPartnerSoftLimitMonthly(e.target.value)}
                    placeholder="leave blank to unset"
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
                <label className="text-[11px] text-textMute">
                  Overage
                  <select
                    value={partnerOverageEnabled}
                    onChange={(e) =>
                      setPartnerOverageEnabled(e.target.value as "enabled" | "disabled")
                    }
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
                    onChange={(e) => setPartnerOveragePriceCents(e.target.value)}
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
                    onChange={(e) => setPartnerOverageUnitQuantity(e.target.value)}
                    className="mt-1 w-full rounded border border-borderTone bg-panel px-2 py-1 text-xs text-textMain"
                  />
                </label>
              </div>
            </>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => void runIssuePartnerKey()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Issue API Key"}
          </button>
          <button
            onClick={() => void runUpdatePartnerEntitlement()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Save API Entitlement"}
          </button>
        </div>
      </div>
    </div>
  );
}
