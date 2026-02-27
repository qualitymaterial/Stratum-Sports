"use client";

import {
  cancelAdminUserBilling,
  reactivateAdminUserBilling,
  resyncAdminUserBilling,
} from "@/lib/api";
import { useAdminContext } from "./AdminContext";
import { AdminUserSearch } from "./AdminUserSearch";
import { AdminMutationControls } from "./AdminMutationControls";

export function AdminBillingTab() {
  const ctx = useAdminContext();

  const runBillingResync = async () => {
    await ctx.executeMutation(async () => {
      const result = await resyncAdminUserBilling(ctx.token, ctx.mutationUserId.trim(), {
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.refreshBilling();
      return `Billing resync completed for ${result.email}, operation ${result.operation}, action ${result.action_id}`;
    });
  };

  const runBillingCancel = async () => {
    await ctx.executeMutation(async () => {
      const result = await cancelAdminUserBilling(ctx.token, ctx.mutationUserId.trim(), {
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.refreshBilling();
      return `Billing cancel scheduled for ${result.email}, action ${result.action_id}`;
    });
  };

  const runBillingReactivate = async () => {
    await ctx.executeMutation(async () => {
      const result = await reactivateAdminUserBilling(ctx.token, ctx.mutationUserId.trim(), {
        reason: ctx.mutationReason.trim(),
        step_up_password: ctx.mutationStepUpPassword,
        confirm_phrase: ctx.mutationConfirmPhrase.trim(),
      });
      ctx.refreshBilling();
      return `Billing reactivated for ${result.email}, action ${result.action_id}`;
    });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">Billing Management</p>
        <p className="mt-2 text-xs text-textMute">
          Search for a user, then view their billing snapshot and perform billing actions.
        </p>

        <div className="mt-4">
          <AdminUserSearch />
        </div>

        <AdminMutationControls />

        <div className="mt-4 rounded border border-borderTone bg-panelSoft p-3 text-xs text-textMute">
          <div className="flex items-center justify-between gap-3">
            <p className="uppercase tracking-wider">Billing Snapshot</p>
            <button
              onClick={() => ctx.refreshBilling()}
              disabled={ctx.billingLoading || !ctx.mutationUserId.trim()}
              className="rounded border border-borderTone px-2 py-1 text-[10px] uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              {ctx.billingLoading ? "Loading..." : "Refresh Billing"}
            </button>
          </div>
          {ctx.billingError && <p className="mt-2 text-negative">{ctx.billingError}</p>}
          {!ctx.billingError && (
            <div className="mt-2 space-y-1">
              <p>
                Customer:{" "}
                <span className="text-textMain">{ctx.billingSummary?.stripe_customer_id ?? "-"}</span>
              </p>
              <p>
                Subscription ID:{" "}
                <span className="text-textMain">
                  {ctx.billingSummary?.subscription?.stripe_subscription_id ?? "-"}
                </span>
              </p>
              <p>
                Status:{" "}
                <span className="text-textMain">{ctx.billingSummary?.subscription?.status ?? "-"}</span>
                {" • "}Cancel at period end:{" "}
                <span className="text-textMain">
                  {ctx.billingSummary?.subscription
                    ? ctx.billingSummary.subscription.cancel_at_period_end
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
            onClick={() => void runBillingResync()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Resync Billing"}
          </button>
          <button
            onClick={() => void runBillingCancel()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Cancel Subscription"}
          </button>
          <button
            onClick={() => void runBillingReactivate()}
            disabled={ctx.mutationLoading}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            {ctx.mutationLoading ? "Working..." : "Reactivate Subscription"}
          </button>
        </div>
      </div>
    </div>
  );
}
