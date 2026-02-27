"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getMfaStatus,
  startMfaEnrollment,
  confirmMfaEnrollment,
  disableMfa,
  regenerateBackupCodes,
  MfaStatus,
} from "@/lib/api";

type EnrollState =
  | { step: "idle" }
  | { step: "pending"; totp_secret: string; provisioning_uri: string }
  | { step: "backup_codes"; codes: string[] };

export function AdminSecurityTab({ token }: { token: string }) {
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [enrollState, setEnrollState] = useState<EnrollState>({ step: "idle" });
  const [totpCode, setTotpCode] = useState("");
  const [actionPassword, setActionPassword] = useState("");
  const [actionMfaCode, setActionMfaCode] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await getMfaStatus(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MFA status");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const handleStartEnroll = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const result = await startMfaEnrollment(token);
      setEnrollState({ step: "pending", totp_secret: result.totp_secret, provisioning_uri: result.provisioning_uri });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start enrollment");
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmEnroll = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const result = await confirmMfaEnrollment(token, totpCode);
      setEnrollState({ step: "backup_codes", codes: result.backup_codes });
      setTotpCode("");
      setSuccess("MFA enrolled successfully.");
      void loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid TOTP code");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisable = async () => {
    setActionLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await disableMfa(token, { password: actionPassword, mfa_code: actionMfaCode });
      setActionPassword("");
      setActionMfaCode("");
      setSuccess("MFA disabled.");
      void loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable MFA");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setActionLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await regenerateBackupCodes(token, { password: actionPassword, mfa_code: actionMfaCode });
      setEnrollState({ step: "backup_codes", codes: result.backup_codes });
      setActionPassword("");
      setActionMfaCode("");
      setSuccess("Backup codes regenerated.");
      void loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to regenerate backup codes");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-sm text-textMute">Loading MFA status...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Status Card */}
      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <h2 className="text-sm font-semibold text-textMain">Multi-Factor Authentication</h2>
        {status && (
          <div className="mt-3 space-y-1 text-sm">
            <p>
              Status:{" "}
              <span className={status.mfa_enabled ? "text-positive" : "text-textMute"}>
                {status.mfa_enabled ? "Enabled" : "Disabled"}
              </span>
            </p>
            {status.mfa_enrolled_at && (
              <p className="text-textMute">Enrolled: {new Date(status.mfa_enrolled_at).toLocaleString()}</p>
            )}
            {status.mfa_enabled && (
              <p className="text-textMute">Backup codes remaining: {status.backup_codes_remaining}</p>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}
      {success && <p className="text-sm text-positive">{success}</p>}

      {/* Enrollment Flow */}
      {status && !status.mfa_enabled && enrollState.step === "idle" && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <h3 className="text-sm font-semibold text-textMain">Enable MFA</h3>
          <p className="mt-1 text-xs text-textMute">
            Protect your admin account with a TOTP authenticator app.
          </p>
          <button
            onClick={() => void handleStartEnroll()}
            disabled={actionLoading}
            className="mt-3 rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
          >
            {actionLoading ? "Starting..." : "Start Enrollment"}
          </button>
        </div>
      )}

      {enrollState.step === "pending" && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <h3 className="text-sm font-semibold text-textMain">Scan or Enter Secret</h3>
          <p className="mt-1 text-xs text-textMute">
            Add this to your authenticator app (Google Authenticator, Authy, 1Password, etc.).
          </p>
          <div className="mt-3 space-y-2">
            <label className="block text-xs text-textMute">
              TOTP Secret (copy into your app)
              <input
                readOnly
                value={enrollState.totp_secret}
                onClick={(e) => (e.target as HTMLInputElement).select()}
                className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm text-textMain"
              />
            </label>
            <details className="text-xs text-textMute">
              <summary className="cursor-pointer hover:text-textMain">Show provisioning URI</summary>
              <input
                readOnly
                value={enrollState.provisioning_uri}
                onClick={(e) => (e.target as HTMLInputElement).select()}
                className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-xs text-textMain"
              />
            </details>
          </div>
          <div className="mt-4">
            <label className="block text-xs text-textMute">
              Enter 6-digit code from your app
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                maxLength={6}
                placeholder="000000"
                className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-center font-mono text-lg tracking-[0.3em] text-textMain outline-none transition focus:border-accent"
              />
            </label>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => void handleConfirmEnroll()}
                disabled={actionLoading || totpCode.length < 6}
                className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
              >
                {actionLoading ? "Verifying..." : "Verify & Enable"}
              </button>
              <button
                onClick={() => {
                  setEnrollState({ step: "idle" });
                  setTotpCode("");
                }}
                className="rounded-md border border-borderTone px-3 py-1.5 text-sm text-textMute transition hover:bg-borderTone/30"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Backup Codes Display */}
      {enrollState.step === "backup_codes" && (
        <div className="rounded-xl border border-accent/30 bg-panel p-5 shadow-terminal">
          <h3 className="text-sm font-semibold text-accent">Save Your Backup Codes</h3>
          <p className="mt-1 text-xs text-textMute">
            Store these in a safe place. Each code can only be used once. You will not see these again.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {enrollState.codes.map((code) => (
              <code
                key={code}
                className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-center font-mono text-sm text-textMain"
              >
                {code}
              </code>
            ))}
          </div>
          <button
            onClick={() => setEnrollState({ step: "idle" })}
            className="mt-4 rounded-md border border-borderTone px-3 py-1.5 text-sm text-textMute transition hover:bg-borderTone/30"
          >
            I&apos;ve saved these codes
          </button>
        </div>
      )}

      {/* Disable / Regenerate Actions */}
      {status?.mfa_enabled && enrollState.step !== "backup_codes" && (
        <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
          <h3 className="text-sm font-semibold text-textMain">MFA Actions</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-textMute">
              Your Password
              <input
                type="password"
                autoComplete="current-password"
                value={actionPassword}
                onChange={(e) => setActionPassword(e.target.value)}
                className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
              />
            </label>
            <label className="text-xs text-textMute">
              Current MFA Code
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={actionMfaCode}
                onChange={(e) => setActionMfaCode(e.target.value)}
                maxLength={8}
                placeholder="000000"
                className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm tracking-wider text-textMain"
              />
            </label>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => void handleRegenerate()}
              disabled={actionLoading || actionPassword.length < 8 || actionMfaCode.length < 6}
              className="rounded-md border border-borderTone px-3 py-1.5 text-sm text-textMute transition hover:bg-borderTone/30 disabled:opacity-60"
            >
              {actionLoading ? "Regenerating..." : "Regenerate Backup Codes"}
            </button>
            <button
              onClick={() => void handleDisable()}
              disabled={actionLoading || actionPassword.length < 8 || actionMfaCode.length < 6}
              className="rounded-md border border-negative/40 px-3 py-1.5 text-sm text-negative transition hover:bg-negative/10 disabled:opacity-60"
            >
              {actionLoading ? "Disabling..." : "Disable MFA"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
