"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { getDiscordAuthUrl, login, mfaVerify } from "@/lib/api";
import { setSession } from "@/lib/auth";

const DISCORD_STATE_KEY = "stratum_discord_oauth_state";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [mfaChallengeToken, setMfaChallengeToken] = useState("");
  const [mfaCode, setMfaCode] = useState("");

  const onDiscordLogin = async () => {
    try {
      const { url, state } = await getDiscordAuthUrl();
      sessionStorage.setItem(DISCORD_STATE_KEY, state);
      window.location.href = url;
    } catch (err) {
      setError("Failed to start Discord login");
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const result = await login(email, password);
      if (result.mfa_required && result.mfa_challenge_token) {
        setMfaChallengeToken(result.mfa_challenge_token);
        setSubmitting(false);
        return;
      }
      setSession(result.access_token!, result.user!);
      router.push("/app/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const onMfaSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const result = await mfaVerify(mfaChallengeToken, mfaCode);
      setSession(result.access_token, result.user);
      router.push("/app/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid MFA code");
    } finally {
      setSubmitting(false);
    }
  };

  if (mfaChallengeToken) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
        <div className="w-full rounded-2xl border border-borderTone bg-panel p-8 shadow-terminal">
          <p className="text-xs uppercase tracking-[0.28em] text-textMute">Stratum Sports</p>
          <h1 className="mt-3 text-2xl font-semibold text-textMain">MFA Verification</h1>
          <p className="mt-2 text-sm text-textMute">Enter the 6-digit code from your authenticator app.</p>

          <form onSubmit={onMfaSubmit} className="mt-8 space-y-4">
            <div>
              <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">MFA Code</label>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                required
                maxLength={8}
                className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-center font-mono text-lg tracking-[0.3em] outline-none transition focus:border-accent"
                placeholder="000000"
              />
            </div>

            {error && <p className="text-sm text-negative">{error}</p>}

            <button
              type="submit"
              disabled={submitting || mfaCode.length < 6}
              className="w-full rounded-md border border-accent bg-accent/10 px-3 py-2 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
            >
              {submitting ? "Verifying..." : "Verify"}
            </button>
          </form>

          <button
            type="button"
            onClick={() => {
              setMfaChallengeToken("");
              setMfaCode("");
              setError("");
            }}
            className="mt-4 w-full text-sm text-textMute hover:text-textMain"
          >
            Back to login
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
      <div className="w-full rounded-2xl border border-borderTone bg-panel p-8 shadow-terminal">
        <p className="text-xs uppercase tracking-[0.28em] text-textMute">Stratum Sports</p>
        <h1 className="mt-3 text-2xl font-semibold text-textMain">Sign In</h1>
        <p className="mt-2 text-sm text-textMute">Institutional-grade market intelligence infrastructure.</p>

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

          <div>
            <label className="mb-2 block text-xs uppercase tracking-wider text-textMute">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm outline-none transition focus:border-accent"
            />
          </div>

          {error && <p className="text-sm text-negative">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md border border-accent bg-accent/10 px-3 py-2 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-borderTone" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-panel px-2 text-textMute">Or continue with</span>
          </div>
        </div>

        <button
          onClick={() => {
            void onDiscordLogin();
          }}
          className="flex w-full items-center justify-center gap-3 rounded-md border border-borderTone bg-panelSoft px-3 py-2 text-sm font-medium text-textMain transition hover:bg-borderTone/30"
        >
          <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
          </svg>
          Discord
        </button>

        <p className="mt-6 text-sm text-textMute">
          Need an account?{" "}
          <Link href="/register" className="text-accent hover:underline">
            Register
          </Link>
        </p>
        <p className="mt-2 text-sm text-textMute">
          Forgot password?{" "}
          <Link href="/forgot-password" className="text-accent hover:underline">
            Reset it
          </Link>
        </p>
      </div>
    </main>
  );
}
