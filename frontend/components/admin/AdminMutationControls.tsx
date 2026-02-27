"use client";

import { useAdminContext } from "./AdminContext";

export function AdminMutationControls() {
  const ctx = useAdminContext();

  return (
    <>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="text-xs text-textMute">
          Target User ID (auto-filled)
          <input
            value={ctx.mutationUserId}
            onChange={(e) => {
              ctx.setMutationUserId(e.target.value);
            }}
            placeholder="uuid"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Audit Reason
          <input
            value={ctx.mutationReason}
            onChange={(e) => ctx.setMutationReason(e.target.value)}
            placeholder="Explain why this action is needed"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Step-up Password (Your Password)
          <input
            type="password"
            autoComplete="current-password"
            value={ctx.mutationStepUpPassword}
            onChange={(e) => ctx.setMutationStepUpPassword(e.target.value)}
            placeholder="Enter your current password"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Type CONFIRM
          <input
            value={ctx.mutationConfirmPhrase}
            onChange={(e) => ctx.setMutationConfirmPhrase(e.target.value)}
            placeholder="CONFIRM"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
      </div>
      {ctx.user.mfa_enabled && (
        <label className="mt-3 block text-xs text-textMute">
          MFA Code (from your authenticator app)
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={ctx.mutationMfaCode}
            onChange={(e) => ctx.setMutationMfaCode(e.target.value)}
            placeholder="000000"
            maxLength={8}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm tracking-wider text-textMain"
          />
        </label>
      )}
      {ctx.mutationError && <p className="mt-2 text-sm text-negative">{ctx.mutationError}</p>}
      {ctx.mutationResult && <p className="mt-2 text-sm text-positive">{ctx.mutationResult}</p>}
    </>
  );
}
