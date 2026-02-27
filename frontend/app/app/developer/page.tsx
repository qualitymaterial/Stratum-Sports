"use client";

import { useEffect, useState } from "react";
import {
    getPartnerBillingSummary,
    getPartnerWebhooks,
    getPartnerWebhookLogs,
    createPartnerWebhook,
    updatePartnerWebhook,
    deletePartnerWebhook,
    rotatePartnerWebhookSecret,
    createPartnerPortalSession
} from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { LoadingState } from "@/components/LoadingState";
import { PartnerBillingSummary, WebhookOut, WebhookLogOut } from "@/lib/types";

export default function DeveloperPage() {
    const { token, loading } = useCurrentUser(true);
    const [summary, setSummary] = useState<PartnerBillingSummary | null>(null);
    const [webhooks, setWebhooks] = useState<WebhookOut[]>([]);
    const [logs, setLogs] = useState<WebhookLogOut[]>([]);
    const [loadingInitial, setLoadingInitial] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [revealingSecret, setRevealingSecret] = useState<string | null>(null);
    const [showAddForm, setShowAddForm] = useState(false);
    const [newWebhook, setNewWebhook] = useState({ url: "", description: "" });
    const [addingWebhook, setAddingWebhook] = useState(false);

    useEffect(() => {
        if (!loading && token) {
            load();
        }
    }, [loading, token]);

    async function load() {
        try {
            if (!token) return;
            setLoadingInitial(true);
            const [sum, whs, lg] = await Promise.all([
                getPartnerBillingSummary(token),
                getPartnerWebhooks(token),
                getPartnerWebhookLogs(token)
            ]);
            setSummary(sum);
            setWebhooks(whs);
            setLogs(lg);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load developer data");
        } finally {
            setLoadingInitial(false);
        }
    }

    const handleCreateWebhook = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token) return;
        setAddingWebhook(true);
        try {
            const created = await createPartnerWebhook(token, newWebhook);
            setWebhooks([...webhooks, created]);
            setNewWebhook({ url: "", description: "" });
            setShowAddForm(false);
        } catch (err) {
            alert(err instanceof Error ? err.message : "Failed to create webhook");
        } finally {
            setAddingWebhook(false);
        }
    };

    const handleToggleWebhook = async (wh: WebhookOut) => {
        if (!token) return;
        try {
            const updated = await updatePartnerWebhook(token, wh.id, { is_active: !wh.is_active });
            setWebhooks(webhooks.map(w => w.id === wh.id ? updated : w));
        } catch (err) {
            alert(err instanceof Error ? err.message : "Failed to update webhook");
        }
    };

    const handleDeleteWebhook = async (id: string) => {
        if (!confirm("Are you sure you want to delete this webhook?")) return;
        if (!token) return;
        try {
            await deletePartnerWebhook(token, id);
            setWebhooks(webhooks.filter(w => w.id !== id));
        } catch (err) {
            alert(err instanceof Error ? err.message : "Failed to delete webhook");
        }
    };

    const handleRotateSecret = async (id: string) => {
        if (!confirm("Rotate secret? Existing integrations will break immediately.")) return;
        if (!token) return;
        try {
            const updated = await rotatePartnerWebhookSecret(token, id);
            setWebhooks(webhooks.map(w => w.id === id ? updated : w));
        } catch (err) {
            alert(err instanceof Error ? err.message : "Failed to rotate secret");
        }
    };

    const handleBillingPortal = async () => {
        if (!token) return;
        try {
            const { url } = await createPartnerPortalSession(token);
            window.location.href = url;
        } catch (err) {
            alert(err instanceof Error ? err.message : "Failed to open billing portal");
        }
    };

    if (loading || loadingInitial) return <LoadingState label="Provisioning developer portal..." />;

    const usage = summary?.current_usage;
    const plan = summary?.plan;

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-textMain">Infrastructure Portal</h1>
                    <p className="text-textMute mt-1">Manage your real-time data webhooks and monitor API consumption.</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={load}
                        className="px-4 py-2 text-sm bg-panel border border-borderTone hover:border-accent hover:text-accent rounded-lg transition-all"
                    >
                        Refresh
                    </button>
                    <button
                        onClick={handleBillingPortal}
                        className="px-4 py-2 text-sm bg-accent text-bg font-bold rounded-lg hover:shadow-[0_0_15px_rgba(71,199,166,0.3)] transition-all"
                    >
                        API Billing
                    </button>
                </div>
            </header>

            {error && (
                <div className="p-4 bg-negative/10 border border-negative/30 text-negative rounded-xl text-sm">
                    {error}
                </div>
            )}

            {/* Grid Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

                {/* Left Column: Webhooks & Keys */}
                <div className="lg:col-span-2 space-y-8">

                    {/* Webhooks Section */}
                    <section className="bg-panel/40 backdrop-blur-md border border-borderTone rounded-2xl overflow-hidden shadow-xl">
                        <div className="px-6 py-5 border-b border-borderTone flex justify-between items-center bg-panel/20">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                                Real-time Webhooks
                            </h2>
                            <button
                                onClick={() => setShowAddForm(!showAddForm)}
                                className="text-xs font-bold uppercase tracking-wider text-accent hover:text-accent/80 transition-colors"
                                disabled={webhooks.length >= 5}
                            >
                                {showAddForm ? "Cancel" : "Add Webhook"}
                            </button>
                        </div>

                        <div className="p-6">
                            {showAddForm && (
                                <form onSubmit={handleCreateWebhook} className="mb-8 p-5 bg-panelSoft/50 border border-accent/20 rounded-xl space-y-4 animate-in slide-in-from-top-2">
                                    <div className="space-y-1">
                                        <label className="text-xs font-bold text-textMute uppercase">Endpoint URL</label>
                                        <input
                                            type="url"
                                            required
                                            placeholder="https://your-domain.com/hooks/stratum"
                                            className="w-full bg-bg border border-borderTone focus:border-accent outline-none px-4 py-2.5 rounded-lg text-sm transition-colors"
                                            value={newWebhook.url}
                                            onChange={e => setNewWebhook({ ...newWebhook, url: e.target.value })}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-xs font-bold text-textMute uppercase">Description (Optional)</label>
                                        <input
                                            type="text"
                                            placeholder="Production Signal Sync"
                                            className="w-full bg-bg border border-borderTone focus:border-accent outline-none px-4 py-2.5 rounded-lg text-sm transition-colors"
                                            value={newWebhook.description}
                                            onChange={e => setNewWebhook({ ...newWebhook, description: e.target.value })}
                                        />
                                    </div>
                                    <button
                                        disabled={addingWebhook}
                                        className="w-full py-2.5 bg-accent text-bg font-bold rounded-lg disabled:opacity-50 transition-all hover:brightness-110"
                                    >
                                        {addingWebhook ? "Creating..." : "Create Webhook"}
                                    </button>
                                </form>
                            )}

                            {webhooks.length === 0 && !showAddForm ? (
                                <div className="text-center py-12 border-2 border-dashed border-borderTone rounded-xl">
                                    <p className="text-textMute text-sm">No webhooks configured.</p>
                                    <p className="text-xs text-textMute/60 mt-2">Add an endpoint to start receiving real-time signals.</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {webhooks.map(wh => (
                                        <div key={wh.id} className="group p-4 bg-panelSoft/30 border border-borderTone hover:border-borderTone/80 rounded-xl transition-all">
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="space-y-1 flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <div className={`h-2 w-2 rounded-full ${wh.is_active ? "bg-positive shadow-[0_0_8px_rgba(76,212,131,0.5)]" : "bg-textMute"}`} />
                                                        <h3 className="font-medium text-sm truncate">{wh.url}</h3>
                                                    </div>
                                                    <p className="text-xs text-textMute truncate pl-4">{wh.description || "No description"}</p>
                                                </div>
                                                <div className="flex gap-2 opacity-50 group-hover:opacity-100 transition-opacity">
                                                    <button
                                                        onClick={() => handleToggleWebhook(wh)}
                                                        className="p-1.5 hover:bg-panel rounded-lg text-textMute hover:text-textMain transition-colors"
                                                        title={wh.is_active ? "Deactivate" : "Activate"}
                                                    >
                                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636" />
                                                        </svg>
                                                    </button>
                                                    <button
                                                        onClick={() => handleDeleteWebhook(wh.id)}
                                                        className="p-1.5 hover:bg-negative/10 rounded-lg text-textMute hover:text-negative transition-colors"
                                                        title="Delete"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                        </svg>
                                                    </button>
                                                </div>
                                            </div>

                                            <div className="mt-4 flex flex-wrap items-center gap-4 text-[10px] font-mono text-textMute/80">
                                                <div className="flex items-center gap-2 bg-bg px-2 py-1 rounded border border-borderTone">
                                                    <span className="uppercase text-[9px] font-bold text-accent px-1 border-r border-borderTone mr-1">Secret</span>
                                                    <span className="select-all">
                                                        {revealingSecret === wh.id ? wh.secret : "whsec_••••••••••••••••••••••••••••"}
                                                    </span>
                                                    <button
                                                        onMouseDown={() => setRevealingSecret(wh.id)}
                                                        onMouseUp={() => setRevealingSecret(null)}
                                                        onMouseLeave={() => setRevealingSecret(null)}
                                                        className="ml-1 hover:text-accent transition-colors"
                                                    >
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                                        </svg>
                                                    </button>
                                                </div>
                                                <button
                                                    onClick={() => handleRotateSecret(wh.id)}
                                                    className="hover:text-accent flex items-center gap-1 transition-colors"
                                                >
                                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                                    </svg>
                                                    Rotate
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </section>

                    {/* Activity Logs Section */}
                    <section className="bg-panel/40 backdrop-blur-md border border-borderTone rounded-2xl overflow-hidden shadow-xl">
                        <div className="px-6 py-5 border-b border-borderTone flex justify-between items-center bg-panel/20">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                                Delivery Logs
                            </h2>
                            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-positive/10 border border-positive/20 text-[10px] text-positive font-bold uppercase tracking-widest animate-pulse">
                                Live Stream Active
                            </div>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-xs border-collapse">
                                <thead className="text-textMute font-bold uppercase tracking-wider bg-panelSoft/50 border-b border-borderTone">
                                    <tr>
                                        <th className="px-6 py-4">Status</th>
                                        <th className="px-6 py-4">Webhook</th>
                                        <th className="px-6 py-4">Latency</th>
                                        <th className="px-6 py-4 text-right">Timestamp</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-borderTone/40">
                                    {logs.length === 0 ? (
                                        <tr>
                                            <td colSpan={4} className="px-6 py-12 text-center text-textMute italic">No delivery events yet.</td>
                                        </tr>
                                    ) : (
                                        logs.map(log => (
                                            <tr key={log.id} className="hover:bg-panelSoft/20 transition-colors">
                                                <td className="px-6 py-3">
                                                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-mono font-bold ${log.status_code && log.status_code < 300 ? "text-positive bg-positive/10" : "text-negative bg-negative/10"}`}>
                                                        {log.status_code || "FAIL"}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-3 text-textMute font-mono max-w-[200px] truncate">
                                                    ID: {log.webhook_id.split('-')[0]}...
                                                </td>
                                                <td className="px-6 py-3 text-textMute font-mono">
                                                    {log.duration_ms}ms
                                                </td>
                                                <td className="px-6 py-3 text-right text-textMute/70">
                                                    {new Date(log.created_at).toLocaleTimeString()}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </section>

                </div>

                {/* Right Column: Key Stats & Plan */}
                <div className="space-y-8">

                    {/* Usage Stats Card */}
                    <section className="bg-panel/40 backdrop-blur-md border border-borderTone rounded-2xl p-6 shadow-xl relative overflow-hidden group">
                        {/* Gloss Header */}
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent/0 via-accent/40 to-accent/0" />

                        <h2 className="text-lg font-semibold mb-6">API Consumption</h2>

                        <div className="space-y-6">
                            <div>
                                <div className="flex justify-between items-end mb-2">
                                    <p className="text-xs font-bold text-textMute uppercase tracking-widest">Monthly Quota</p>
                                    <p className="text-sm font-bold text-textMain">
                                        {usage?.request_count.toLocaleString()} / {usage?.included_limit.toLocaleString()}
                                    </p>
                                </div>
                                <div className="h-3 bg-bg border border-borderTone rounded-full overflow-hidden">
                                    <div
                                        className={`h-full bg-gradient-to-r from-accent/60 to-accent shadow-[0_0_10px_rgba(71,199,166,0.2)] rounded-full transition-all duration-1000`}
                                        style={{ width: `${Math.min(100, (usage?.request_count || 0) / (usage?.included_limit || 1) * 100)}%` }}
                                    />
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div className="p-3 bg-panelSoft/50 border border-borderTone rounded-xl">
                                    <p className="text-[10px] font-bold text-textMute uppercase tracking-wider">Remaining</p>
                                    <p className="text-xl font-bold mt-1 text-positive">{(usage?.remaining || 0).toLocaleString()}</p>
                                </div>
                                <div className="p-3 bg-panelSoft/50 border border-borderTone rounded-xl">
                                    <p className="text-[10px] font-bold text-textMute uppercase tracking-wider">Overage</p>
                                    <p className="text-xl font-bold mt-1 text-negative">{(usage?.overage_count || 0).toLocaleString()}</p>
                                </div>
                            </div>

                            <div className="pt-4 border-t border-borderTone/40">
                                <div className="flex justify-between text-xs py-1">
                                    <span className="text-textMute">Billing Period</span>
                                    <span className="text-textMain font-mono">{usage?.month || "--"}</span>
                                </div>
                                <div className="flex justify-between text-xs py-1">
                                    <span className="text-textMute">Soft Limit Threshold</span>
                                    <span className="text-textMain font-mono">{plan?.soft_limit_monthly?.toLocaleString() || "None"}</span>
                                </div>
                                <div className="flex justify-between text-xs py-1">
                                    <span className="text-textMute">Anomaly Alert Level</span>
                                    <span className="text-positive text-[10px] font-bold uppercase tracking-widest">Active (90%)</span>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Plan Details Card */}
                    <section className="bg-panel border border-borderTone rounded-2xl p-6 shadow-xl relative hero-shell overflow-hidden">
                        <h2 className="text-lg font-semibold mb-4">Infrastructure Tier</h2>
                        <div className="space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-xl bg-accent/20 flex items-center justify-center border border-accent/30 text-accent font-bold text-xl">
                                    {plan?.plan_code?.charAt(0).toUpperCase() || "?"}
                                </div>
                                <div>
                                    <p className="text-sm font-bold text-textMain uppercase tracking-widest">
                                        {plan?.plan_code?.replace('_', ' ') || "Free Tier"}
                                    </p>
                                    <p className="text-xs text-accent font-medium">Enterprise Grade</p>
                                </div>
                            </div>

                            <ul className="space-y-2.5">
                                {[
                                    "Real-time Webhook Engine",
                                    "120 Req/Min Rate Limit",
                                    "HMAC-SHA256 Signing",
                                    "Unlimited Multi-book Sync",
                                    "Priority Backfill Access"
                                ].map((feat, i) => (
                                    <li key={i} className="flex items-center gap-2 text-xs text-textMute">
                                        <svg className="w-3.5 h-3.5 text-accent/60" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                        </svg>
                                        {feat}
                                    </li>
                                ))}
                            </ul>

                            <button
                                onClick={handleBillingPortal}
                                className="w-full mt-4 py-2 border border-borderTone hover:border-accent hover:text-accent rounded-lg text-xs font-bold transition-all"
                            >
                                Manage Subscription
                            </button>
                        </div>
                    </section>

                    {/* Docs Deep-link */}
                    <section className="bg-bg border border-borderTone rounded-2xl p-6 shadow-lg">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-textMute mb-3">Quickstart</h3>
                        <div className="space-y-3">
                            <a href="#" className="block p-3 bg-panelSoft/40 hover:bg-panelSoft/70 border border-borderTone rounded-lg transition-colors group">
                                <p className="text-xs font-bold text-textMain group-hover:text-accent transition-colors">Webhook Guide</p>
                                <p className="text-[10px] text-textMute mt-0.5">Learn how to verify signatures and parse payloads.</p>
                            </a>
                            <a href="#" className="block p-3 bg-panelSoft/40 hover:bg-panelSoft/70 border border-borderTone rounded-lg transition-colors group">
                                <p className="text-xs font-bold text-textMain group-hover:text-accent transition-colors">API Reference</p>
                                <p className="text-[10px] text-textMute mt-0.5">Explore the /intel endpoints and parameters.</p>
                            </a>
                        </div>
                    </section>

                </div>

            </div>

            <style jsx>{`
        @keyframes flash-green {
          0% { background-color: rgba(76, 212, 131, 0.4); }
          100% { background-color: transparent; }
        }
        .animate-flash-green {
          animation: flash-green 1.5s ease-out;
        }
      `}</style>
        </div>
    );
}
