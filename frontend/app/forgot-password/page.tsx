"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setStatus("");
    setError("");
    setResetToken("");
    try {
      const response = await requestPasswordReset(email);
      setStatus(response.message || "If this email exists, a password reset was requested.");
      if (response.reset_token) {
        setResetToken(response.reset_token);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request reset");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
      <div className="w-full rounded-2xl border border-borderTone bg-panel p-8 shadow-terminal">
        <p className="text-xs uppercase tracking-[0.28em] text-textMute">Stratum Sports</p>
        <h1 className="mt-3 text-2xl font-semibold text-textMain">Reset Password</h1>
        <p className="mt-2 text-sm text-textMute">Enter your account email to request a reset token.</p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm outline-none transition focus:border-accent"
            />
          </div>

          {error && <p className="text-sm text-negative">{error}</p>}
          {status && <p className="text-sm text-accent">{status}</p>}

          {resetToken && (
            <p className="text-xs text-textMute">
              Development reset token generated. Continue here:{" "}
              <Link href={`/reset-password?token=${encodeURIComponent(resetToken)}`} className="text-accent hover:underline">
                Open reset form
              </Link>
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md border border-accent bg-accent/10 px-3 py-2 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
          >
            {submitting ? "Requesting..." : "Request Reset"}
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
