"use client";

import { useEffect, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { getDiscordConnection, upsertDiscordConnection } from "@/lib/api";
import { hasProAccess } from "@/lib/access";
import { useCurrentUser } from "@/lib/auth";
import { DiscordConnection } from "@/lib/types";

const DEFAULT_FORM = {
  webhook_url: "",
  is_enabled: true,
  alert_spreads: true,
  alert_totals: true,
  alert_multibook: true,
  min_strength: 60,
  min_books_affected: 1,
  max_dispersion: "",
  cooldown_minutes: 15,
};

export default function DiscordPage() {
  const { user, loading, token } = useCurrentUser(true);
  const [connection, setConnection] = useState<DiscordConnection | null>(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!token || loading) return;
    void getDiscordConnection(token)
      .then((conn) => {
        setConnection(conn);
        setForm({
          webhook_url: conn.webhook_url,
          is_enabled: conn.is_enabled,
          alert_spreads: conn.alert_spreads,
          alert_totals: conn.alert_totals,
          alert_multibook: conn.alert_multibook,
          min_strength: conn.min_strength,
          min_books_affected: Math.max(1, Number(conn.thresholds?.min_books_affected ?? 1)),
          max_dispersion:
            conn.thresholds?.max_dispersion == null ? "" : String(conn.thresholds.max_dispersion),
          cooldown_minutes: Math.max(0, Number(conn.thresholds?.cooldown_minutes ?? 15)),
        });
      })
      .catch(() => {
        // 404 means no connection yet — start with defaults
      });
  }, [token, loading]);

  const onSave = async () => {
    if (!token) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const conn = await upsertDiscordConnection(token, {
        webhook_url: form.webhook_url,
        is_enabled: form.is_enabled,
        alert_spreads: form.alert_spreads,
        alert_totals: form.alert_totals,
        alert_multibook: form.alert_multibook,
        min_strength: form.min_strength,
        thresholds: {
          min_books_affected: Math.max(1, Number(form.min_books_affected) || 1),
          max_dispersion:
            form.max_dispersion === "" ? null : Math.max(0, Number(form.max_dispersion) || 0),
          cooldown_minutes: Math.max(0, Number(form.cooldown_minutes) || 0),
        },
      });
      setConnection(conn);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !user) {
    return <LoadingState label="Loading Discord settings..." />;
  }
  const proAccess = hasProAccess(user);

  if (!proAccess) {
    return (
      <section className="space-y-4">
        <h1 className="text-xl font-semibold">Discord Alerts</h1>
        <div className="rounded-xl border border-borderTone bg-panel p-6 text-sm text-textMute shadow-terminal">
          <p className="mb-3 font-medium text-textMain">Pro feature</p>
          <p>
            Discord webhook alerts are available on the Pro plan. Upgrade to receive real-time
            signal notifications directly in your server.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Discord Alerts</h1>
        <p className="text-sm text-textMute">
          Send real-time signal notifications to a Discord channel via webhook.
        </p>
      </header>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="mb-4 text-xs uppercase tracking-wider text-textMute">Webhook</p>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-textMute">Webhook URL</label>
            <input
              type="url"
              value={form.webhook_url}
              onChange={(e) => setForm((f) => ({ ...f, webhook_url: e.target.value }))}
              placeholder="https://discord.com/api/webhooks/..."
              className="w-full rounded border border-borderTone bg-panelSoft px-3 py-2 text-sm text-textMain placeholder:text-textMute/50 focus:border-accent focus:outline-none"
            />
          </div>

          <label className="flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={form.is_enabled}
              onChange={(e) => setForm((f) => ({ ...f, is_enabled: e.target.checked }))}
              className="h-4 w-4 accent-accent"
            />
            <span className="text-sm text-textMain">Alerts enabled</span>
          </label>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="mb-4 text-xs uppercase tracking-wider text-textMute">Alert Types</p>
        <div className="space-y-3">
          {(
            [
              { key: "alert_spreads", label: "Spread moves" },
              { key: "alert_totals", label: "Total moves" },
              { key: "alert_multibook", label: "Multibook sync" },
            ] as const
          ).map(({ key, label }) => (
            <label key={key} className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.checked }))}
                className="h-4 w-4 accent-accent"
              />
              <span className="text-sm text-textMain">{label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="mb-4 text-xs uppercase tracking-wider text-textMute">Minimum Strength</p>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={1}
            max={100}
            value={form.min_strength}
            onChange={(e) => setForm((f) => ({ ...f, min_strength: Number(e.target.value) }))}
            className="w-full accent-accent"
          />
          <span className="w-8 text-right text-sm font-semibold text-accent">
            {form.min_strength}
          </span>
        </div>
        <p className="mt-2 text-xs text-textMute">
          Only signals with strength ≥ {form.min_strength} will trigger an alert.
        </p>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="mb-4 text-xs uppercase tracking-wider text-textMute">Noise Controls</p>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="text-xs text-textMute">
            Min Books Affected
            <input
              type="number"
              min={1}
              max={50}
              value={form.min_books_affected}
              onChange={(e) =>
                setForm((f) => ({ ...f, min_books_affected: Math.max(1, Number(e.target.value) || 1) }))
              }
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Max Dispersion
            <input
              type="number"
              min={0}
              step={0.01}
              value={form.max_dispersion}
              onChange={(e) => setForm((f) => ({ ...f, max_dispersion: e.target.value }))}
              placeholder="off"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Cooldown Minutes
            <input
              type="number"
              min={0}
              max={1440}
              value={form.cooldown_minutes}
              onChange={(e) =>
                setForm((f) => ({ ...f, cooldown_minutes: Math.max(0, Number(e.target.value) || 0) }))
              }
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
        </div>
        <p className="mt-2 text-xs text-textMute">
          Reduce alert noise by requiring broader book confirmation, limiting high-dispersion signals, and
          suppressing repeated alerts during cooldown.
        </p>
      </div>

      {error && <p className="text-sm text-negative">{error}</p>}
      {saved && <p className="text-sm text-accent">Settings saved.</p>}

      <button
        disabled={saving || !form.webhook_url.trim()}
        onClick={() => {
          void onSave();
        }}
        className="rounded border border-accent px-4 py-2 text-sm text-accent transition hover:bg-accent/10 disabled:opacity-50"
      >
        {saving ? "Saving…" : connection ? "Update Settings" : "Save Settings"}
      </button>
    </section>
  );
}
