"use client";

import { useState } from "react";

import {
  requestAdminUserPasswordReset,
  updateAdminUserActive,
  updateAdminUserRole,
  updateAdminUserTier,
} from "@/lib/api";
import { hasAdminPermission } from "@/lib/adminPermissions";
import { AdminRole } from "@/lib/types";
import { useAdminContext } from "./AdminContext";
import { AdminUserSearch } from "./AdminUserSearch";
import { AdminMutationControls } from "./AdminMutationControls";

export function AdminUsersTab() {
  const ctx = useAdminContext();

  const [mutationTier, setMutationTier] = useState<"free" | "pro">(
    ctx.selectedUserDefaults?.tier ?? "pro",
  );
  const [mutationRole, setMutationRole] = useState<AdminRole | "none">(
    (ctx.selectedUserDefaults?.role as AdminRole | "none") ?? "support_admin",
  );
  const [mutationActive, setMutationActive] = useState<"active" | "inactive">(
    ctx.selectedUserDefaults?.active ?? "active",
  );

  // Sync defaults when user selection changes
  const prevDefaults = ctx.selectedUserDefaults;
  const [trackedDefaults, setTrackedDefaults] = useState(prevDefaults);
  if (prevDefaults !== trackedDefaults) {
    setTrackedDefaults(prevDefaults);
    if (prevDefaults) {
      setMutationTier(prevDefaults.tier);
      setMutationRole(prevDefaults.role as AdminRole | "none");
      setMutationActive(prevDefaults.active);
    }
  }

  const runTierUpdate = async () => {
    await ctx.executeMutation(async () => {
      const result = await updateAdminUserTier(ctx.token, ctx.mutationUserId.trim(), {
        tier: mutationTier,
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      return `Tier updated: ${result.email} (${result.old_tier} -> ${result.new_tier}), action ${result.action_id}`;
    });
  };

  const runRoleUpdate = async () => {
    await ctx.executeMutation(async () => {
      const result = await updateAdminUserRole(ctx.token, ctx.mutationUserId.trim(), {
        admin_role: mutationRole === "none" ? null : mutationRole,
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      return `Role updated: ${result.email} (${result.old_admin_role ?? "none"} -> ${result.new_admin_role ?? "none"}), action ${result.action_id}`;
    });
  };

  const runActiveUpdate = async () => {
    await ctx.executeMutation(async () => {
      const result = await updateAdminUserActive(ctx.token, ctx.mutationUserId.trim(), {
        is_active: mutationActive === "active",
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      return `Account status updated: ${result.email} (${result.old_is_active ? "active" : "inactive"} -> ${result.new_is_active ? "active" : "inactive"}), action ${result.action_id}`;
    });
  };

  const runPasswordResetRequest = async () => {
    await ctx.executeMutation(async () => {
      const result = await requestAdminUserPasswordReset(ctx.token, ctx.mutationUserId.trim(), {
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      const tokenSuffix =
        result.reset_token && result.expires_in_minutes
          ? ` Reset token: ${result.reset_token} (expires in ${result.expires_in_minutes}m).`
          : "";
      return `Password reset initiated for ${result.email}, action ${result.action_id}.${tokenSuffix}`;
    });
  };

  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <p className="text-xs uppercase tracking-wider text-textMute">User Access Actions</p>
      <p className="mt-2 text-xs text-textMute">
        Changes require a reason, step-up password, and typed confirmation. All actions are recorded
        in immutable admin audit logs.
      </p>

      <div className="mt-4">
        <AdminUserSearch />
      </div>

      <AdminMutationControls />

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="text-xs text-textMute">
          Tier
          <select
            value={mutationTier}
            onChange={(e) => setMutationTier(e.target.value as "free" | "pro")}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          >
            <option value="free">free</option>
            <option value="pro">pro</option>
          </select>
        </label>

        {hasAdminPermission(ctx.user, "user_role_write") && (
          <label className="text-xs text-textMute">
            Admin Role
            <select
              value={mutationRole}
              onChange={(e) => setMutationRole(e.target.value as AdminRole | "none")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="none">none</option>
              <option value="super_admin">super_admin</option>
              <option value="ops_admin">ops_admin</option>
              <option value="support_admin">support_admin</option>
              <option value="billing_admin">billing_admin</option>
            </select>
          </label>
        )}

        {hasAdminPermission(ctx.user, "user_status_write") && (
          <label className="text-xs text-textMute">
            Account Status
            <select
              value={mutationActive}
              onChange={(e) => setMutationActive(e.target.value as "active" | "inactive")}
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            >
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={() => void runTierUpdate()}
          disabled={ctx.mutationLoading}
          className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
        >
          {ctx.mutationLoading ? "Working..." : "Update Tier"}
        </button>

        {hasAdminPermission(ctx.user, "user_role_write") && (
          <button
            onClick={() => void runRoleUpdate()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Update Role"}
          </button>
        )}

        {hasAdminPermission(ctx.user, "user_status_write") && (
          <button
            onClick={() => void runActiveUpdate()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Update Status"}
          </button>
        )}

        {hasAdminPermission(ctx.user, "user_password_reset_write") && (
          <button
            onClick={() => void runPasswordResetRequest()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Initiate Password Reset"}
          </button>
        )}
      </div>
    </div>
  );
}
