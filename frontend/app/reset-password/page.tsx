"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { confirmPasswordReset } from "@/lib/api";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const initialToken = params.get("token");
    if (initialToken && !token) {
      setToken(initialToken);
    }
  }, [token]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setStatus("");

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setSubmitting(true);
    try {
      const response = await confirmPasswordReset(token, newPassword);
      setStatus(response.message || "Password reset successful");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
      <div className="w-full rounded-2xl border border-borderTone bg-panel p-8 shadow-terminal">
        <p className="text-xs uppercase tracking-[0.28em] text-textMute">Stratum Sports</p>
        <h1 className="mt-3 text-2xl font-semibold text-textMain">Set New Password</h1>
        <p className="mt-2 text-sm text-textMute">Use your reset token and choose a new password.</p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">Reset Token</label>
            <input
              type="text"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
              className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm outline-none transition focus:border-accent"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">New Password</label>
            <input
              type="password"
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm outline-none transition focus:border-accent"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">Confirm Password</label>
            <input
              type="password"
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm outline-none transition focus:border-accent"
            />
          </div>

          {error && <p className="text-sm text-negative">{error}</p>}
          {status && <p className="text-sm text-accent">{status}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md border border-accent bg-accent/10 px-3 py-2 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
          >
            {submitting ? "Resetting..." : "Reset Password"}
          </button>
        </form>

        <p className="mt-6 text-sm text-textMute">
          Back to{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
