"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getAdminPollerHealth,
  triggerAdminBackfill,
  replayAdminAlert,
  getAdminOpsTelemetry,
} from "@/lib/api";
import type {
  PollerHealth,
  AdminBackfillTriggerResult,
  AdminAlertReplayResult,
  OpsTelemetry,
  User,
} from "@/lib/types";

// ── Poller Health Section ─────────────────────────────────

function PollerHealthSection({ token }: { token: string }) {
  const [data, setData] = useState<PollerHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(1);
  const [errorsExpanded, setErrorsExpanded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminPollerHealth(token, days));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load poller health");
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-textMain">Poller Health</h2>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded border border-borderTone bg-panelSoft px-2 py-0.5 text-xs text-textMain"
          >
            <option value={1}>1 day</option>
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
          </select>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded border border-borderTone px-2 py-0.5 text-xs text-textMute transition hover:bg-borderTone/30 disabled:opacity-60"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p className="mt-2 text-sm text-negative">{error}</p>}

      {data && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Total Cycles" value={data.cycle_summary.total_cycles} />
            <Stat
              label="Degraded Rate"
              value={`${(data.cycle_summary.degraded_rate * 100).toFixed(1)}%`}
              warn={data.cycle_summary.degraded_rate > 0.1}
            />
            <Stat
              label="Avg Duration"
              value={data.cycle_summary.avg_duration_ms != null ? `${data.cycle_summary.avg_duration_ms.toFixed(0)}ms` : "—"}
            />
            <Stat
              label="Lock Held"
              value={data.lock_held === null ? "Unknown" : data.lock_held ? "Yes" : "No"}
              warn={data.lock_held === true}
            />
          </div>

          {data.cycle_summary.last_cycle_at && (
            <p className="mt-2 text-xs text-textMute">
              Last cycle: {new Date(data.cycle_summary.last_cycle_at).toLocaleString()}
            </p>
          )}

          <div className="mt-3 flex flex-wrap gap-2 text-xs text-textMute">
            <Flag label="Backfill" on={data.backfill_enabled} />
            <Flag label="CLV" on={data.clv_enabled} />
            <Flag label="KPI" on={data.kpi_enabled} />
            <span>Lookback: {data.backfill_lookback_hours}h</span>
            <span>Interval: {data.backfill_interval_minutes}m</span>
          </div>

          {data.recent_errors.length > 0 && (
            <div className="mt-3">
              <button
                onClick={() => setErrorsExpanded(!errorsExpanded)}
                className="text-xs text-negative hover:underline"
              >
                {errorsExpanded ? "Hide" : "Show"} recent errors ({data.recent_errors.length})
              </button>
              {errorsExpanded && (
                <ul className="mt-1 max-h-40 space-y-1 overflow-y-auto text-xs text-textMute">
                  {data.recent_errors.map((e, i) => (
                    <li key={i} className="rounded border border-borderTone bg-panelSoft p-2 font-mono">
                      {e}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Backfill Trigger Section ──────────────────────────────

function BackfillTriggerSection({ token, user }: { token: string; user: User }) {
  const [lookbackHours, setLookbackHours] = useState(72);
  const [maxGames, setMaxGames] = useState(25);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdminBackfillTriggerResult | null>(null);

  const canSubmit =
    reason.length >= 8 && password.length >= 8 && confirmPhrase === "CONFIRM" && !loading;

  const handleTrigger = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await triggerAdminBackfill(token, {
        lookback_hours: lookbackHours,
        max_games: maxGames,
        reason,
        step_up_password: password,
        confirm_phrase: confirmPhrase,
        ...(user.mfa_enabled && mfaCode ? { mfa_code: mfaCode } : {}),
      });
      setResult(res);
      setPassword("");
      setConfirmPhrase("");
      setMfaCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backfill trigger failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <h2 className="text-sm font-semibold text-textMain">Backfill Trigger</h2>
      <p className="mt-1 text-xs text-textMute">
        Manually trigger historical closing consensus backfill for recent games.
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-textMute">
          Lookback Hours (1–720)
          <input
            type="number"
            min={1}
            max={720}
            value={lookbackHours}
            onChange={(e) => setLookbackHours(Number(e.target.value))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Max Games (1–200)
          <input
            type="number"
            min={1}
            max={200}
            value={maxGames}
            onChange={(e) => setMaxGames(Number(e.target.value))}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
      </div>

      <label className="mt-3 block text-xs text-textMute">
        Reason (min 8 chars)
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Re-running backfill after API outage"
          className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
        />
      </label>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="text-xs text-textMute">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Type CONFIRM
          <input
            type="text"
            value={confirmPhrase}
            onChange={(e) => setConfirmPhrase(e.target.value)}
            placeholder="CONFIRM"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        {user.mfa_enabled && (
          <label className="text-xs text-textMute">
            MFA Code
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              maxLength={8}
              placeholder="000000"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm tracking-wider text-textMain"
            />
          </label>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-negative">{error}</p>}

      <button
        onClick={() => void handleTrigger()}
        disabled={!canSubmit}
        className="mt-3 rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
      >
        {loading ? "Triggering..." : "Trigger Backfill"}
      </button>

      {result && (
        <div className="mt-3 rounded border border-positive/30 bg-positive/5 p-3 text-sm">
          <p className="font-medium text-positive">Backfill completed</p>
          <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-textMute sm:grid-cols-4">
            <span>Scanned: {result.games_scanned}</span>
            <span>Backfilled: {result.games_backfilled}</span>
            <span>Skipped: {result.games_skipped}</span>
            <span className={result.errors > 0 ? "text-negative" : ""}>Errors: {result.errors}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Alert Replay Section ──────────────────────────────────

function AlertReplaySection({ token, user }: { token: string; user: User }) {
  const [signalId, setSignalId] = useState("");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdminAlertReplayResult | null>(null);

  const canSubmit =
    signalId.length > 0 && reason.length >= 8 && password.length >= 8 && confirmPhrase === "CONFIRM" && !loading;

  const handleReplay = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await replayAdminAlert(token, {
        signal_id: signalId,
        reason,
        step_up_password: password,
        confirm_phrase: confirmPhrase,
        ...(user.mfa_enabled && mfaCode ? { mfa_code: mfaCode } : {}),
      });
      setResult(res);
      setPassword("");
      setConfirmPhrase("");
      setMfaCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Alert replay failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <h2 className="text-sm font-semibold text-textMain">Alert Replay</h2>
      <p className="mt-1 text-xs text-textMute">
        Re-dispatch Discord alerts for a specific signal, bypassing cooldown.
      </p>

      <label className="mt-3 block text-xs text-textMute">
        Signal ID (UUID)
        <input
          type="text"
          value={signalId}
          onChange={(e) => setSignalId(e.target.value)}
          placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
          className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm text-textMain"
        />
      </label>

      <label className="mt-3 block text-xs text-textMute">
        Reason (min 8 chars)
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Replaying alert missed due to Discord outage"
          className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
        />
      </label>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="text-xs text-textMute">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        <label className="text-xs text-textMute">
          Type CONFIRM
          <input
            type="text"
            value={confirmPhrase}
            onChange={(e) => setConfirmPhrase(e.target.value)}
            placeholder="CONFIRM"
            className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
          />
        </label>
        {user.mfa_enabled && (
          <label className="text-xs text-textMute">
            MFA Code
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              maxLength={8}
              placeholder="000000"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 font-mono text-sm tracking-wider text-textMain"
            />
          </label>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-negative">{error}</p>}

      <button
        onClick={() => void handleReplay()}
        disabled={!canSubmit}
        className="mt-3 rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent transition hover:bg-accent/20 disabled:opacity-60"
      >
        {loading ? "Replaying..." : "Replay Alert"}
      </button>

      {result && (
        <div className="mt-3 rounded border border-positive/30 bg-positive/5 p-3 text-sm">
          <p className="font-medium text-positive">Alert replayed</p>
          <div className="mt-1 space-y-0.5 text-xs text-textMute">
            <p>Signal: {result.signal_type} — Event: {result.event_id}</p>
            <p>
              Sent: {result.sent}{" "}
              {result.failed > 0 && <span className="text-negative">Failed: {result.failed}</span>}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Ops Telemetry Section ─────────────────────────────────

function OpsTelemetrySection({ token }: { token: string }) {
  const [data, setData] = useState<OpsTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminOpsTelemetry(token, days));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load telemetry");
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-textMain">Ops Telemetry</h2>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded border border-borderTone bg-panelSoft px-2 py-0.5 text-xs text-textMain"
          >
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
          </select>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded border border-borderTone px-2 py-0.5 text-xs text-textMute transition hover:bg-borderTone/30 disabled:opacity-60"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p className="mt-2 text-sm text-negative">{error}</p>}

      {data && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat
              label="Alert Failure Rate"
              value={`${(data.alert_failure_rate * 100).toFixed(1)}%`}
              warn={data.alert_failure_rate > 0.05}
            />
            <Stat
              label="Degraded Rate"
              value={`${(data.degraded_rate * 100).toFixed(1)}%`}
              warn={data.degraded_rate > 0.1}
            />
            <Stat
              label="Avg Cycle Duration"
              value={data.avg_cycle_duration_ms != null ? `${data.avg_cycle_duration_ms.toFixed(0)}ms` : "—"}
            />
            <Stat label="Total Cycles" value={data.total_cycles} />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Alerts Sent" value={data.total_alerts_sent} />
            <Stat label="Alerts Failed" value={data.total_alerts_failed} warn={data.total_alerts_failed > 0} />
            <Stat label="Requests Used" value={data.total_requests_used} />
            <Stat
              label="Daily Burn"
              value={data.projected_daily_burn != null ? data.projected_daily_burn.toFixed(0) : "—"}
            />
          </div>

          {(data.latest_requests_remaining != null || data.latest_requests_limit != null) && (
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Remaining" value={data.latest_requests_remaining ?? "—"} />
              <Stat label="Limit" value={data.latest_requests_limit ?? "—"} />
              <Stat
                label="Avg Remaining"
                value={data.avg_requests_remaining != null ? data.avg_requests_remaining.toFixed(0) : "—"}
              />
            </div>
          )}

          <div className="mt-3">
            <p className="text-xs font-medium text-textMute">Feature Flags</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {Object.entries(data.feature_flags).map(([key, val]) => (
                <Flag key={key} label={key.replace(/_/g, " ")} on={val} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Ops Tokens Stub ───────────────────────────────────────

function OpsTokensStub() {
  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <p className="text-xs uppercase tracking-wider text-textMute">Ops Service Tokens</p>
      <p className="mt-3 text-sm text-textMute">
        Ops service token management UI coming soon. Use the API endpoints directly for now:
      </p>
      <ul className="mt-2 space-y-1 text-sm text-textMute">
        <li>
          <code className="text-xs text-accent">GET /api/v1/admin/ops-tokens</code> — list tokens
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens</code> — issue token
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens/:id/revoke</code> — revoke
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens/:id/rotate</code> — rotate
        </li>
      </ul>
    </div>
  );
}

// ── Shared UI helpers ─────────────────────────────────────

function Stat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div>
      <p className="text-xs text-textMute">{label}</p>
      <p className={`text-sm font-medium ${warn ? "text-negative" : "text-textMain"}`}>{value}</p>
    </div>
  );
}

function Flag({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs ${
        on ? "bg-positive/10 text-positive" : "bg-borderTone/30 text-textMute"
      }`}
    >
      {label}: {on ? "ON" : "OFF"}
    </span>
  );
}

// ── Main Tab ──────────────────────────────────────────────

export function AdminOperationsTab({ token, user }: { token: string; user: User }) {
  return (
    <div className="space-y-4">
      <PollerHealthSection token={token} />
      <BackfillTriggerSection token={token} user={user} />
      <AlertReplaySection token={token} user={user} />
      <OpsTelemetrySection token={token} />
      <OpsTokensStub />
    </div>
  );
}
