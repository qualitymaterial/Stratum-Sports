"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useCurrentUser } from "@/lib/auth";
import { hasProAccess } from "@/lib/access";
import { getPublicTeaserKpis, getPublicTopAlphaCapture, getPublicLiquidityHeatmap } from "@/lib/api";
import { PublicTeaserKpisResponse, PublicTopAlphaCapture, PublicLiquidityHeatmap } from "@/lib/types";

const ARTICLES = [
    {
        title: "The Science of CLV",
        description: "Unlike other platforms that focus on \"win rates,\" Stratum focuses on **Closing Line Value (CLV)**. If your entry price is consistently better than the market consensus at kick-off, you have a mathematical edge. Our platform audits thousands of data points daily to ensure our signals capture this edge.",
        link: "/docs/signal-integrity",
        linkText: "Read the Whitepaper",
        stat: "+6.2%",
        statLabel: "Avg Tier-S Alpha",
        statProgress: "w-2/3"
    },
    {
        title: "Structural Core Events",
        description: "Not all line movements are created equal. We classify sharp, coordinated shifts across primary sportsbooks that cross key numbers as 'Structural Core Events'. These represent true market repricing, stripping out recreational noise.",
        link: "/docs/product-tiers",
        linkText: "Learn About Infrastructure",
        stat: "55.0%",
        statLabel: "Base Win Rate",
        statProgress: "w-1/2"
    },
    {
        title: "Market Dislocation Dynamics",
        description: "When a single sportsbook is slow to adjust to a consensus shift, a 'dislocation' occurs. Stratum's low-latency ingestion engine flags these temporary mispricings before they are arbitraged away.",
        link: "/docs/developer-quickstart",
        linkText: "View Developer Docs",
        stat: "< 10s",
        statLabel: "Detection Latency",
        statProgress: "w-5/6"
    }
];

export default function MarketOverviewPage() {
    const { user } = useCurrentUser(true);
    const isPro = hasProAccess(user);

    const [kpis, setKpis] = useState<PublicTeaserKpisResponse | null>(null);
    const [topAlpha, setTopAlpha] = useState<PublicTopAlphaCapture | null>(null);
    const [heatmap, setHeatmap] = useState<PublicLiquidityHeatmap | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeArticleIdx, setActiveArticleIdx] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setActiveArticleIdx((prev) => (prev + 1) % ARTICLES.length);
        }, 8000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        async function fetchData() {
            try {
                const [kpiData, alphaData, heatmapData] = await Promise.all([
                    getPublicTeaserKpis({ window_hours: 24 }),
                    getPublicTopAlphaCapture(),
                    getPublicLiquidityHeatmap()
                ]);
                setKpis(kpiData);
                setTopAlpha(alphaData);
                setHeatmap(heatmapData);
            } catch (err) {
                console.error("Failed to fetch dashboard data", err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, []);

    return (
        <div className="space-y-10 animate-in fade-in duration-700">
            {/* Hero Welcome */}
            <section className="relative p-8 rounded-3xl bg-gradient-to-br from-panelSoft to-bg border border-borderTone/50 overflow-hidden shadow-2xl">
                <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-[100px] -mr-32 -mt-32" />
                <div className="relative z-10">
                    <h1 className="text-4xl font-bold tracking-tight text-textMain">
                        Market Pulse
                    </h1>
                    <p className="text-textMute mt-2 max-w-xl text-lg">
                        Real-time consensus movements and institutional-grade signal tracking.
                    </p>

                    <div className="mt-8 flex flex-wrap gap-4">
                        {!isPro && (
                            <div className="inline-flex items-center gap-4 bg-accent/5 border border-accent/20 px-4 py-2 rounded-full">
                                <span className="flex h-2 w-2 rounded-full bg-accent animate-pulse" />
                                <p className="text-xs font-semibold text-accent uppercase tracking-widest">
                                    Watching Live Markets (10m Delay)
                                </p>
                                <Link href="/app/dashboard" className="text-xs font-bold text-textMain hover:underline ml-2">
                                    Upgrade for Real-time →
                                </Link>
                            </div>
                        )}

                        {/* Live Counter Component */}
                        <div className="inline-flex items-center gap-3 bg-panel/60 border border-borderTone px-4 py-2 rounded-full backdrop-blur-md">
                            <span className="text-xs font-bold text-textMute uppercase tracking-tighter">Live Signals (24h)</span>
                            <span className="text-sm font-black text-textMain">
                                {loading ? "..." : kpis?.signals_in_window?.toLocaleString() || "0"}
                            </span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Alpha Capture Component */}
            {!loading && topAlpha && (
                <section className="bg-accent/5 border border-accent/20 rounded-3xl p-6 flex flex-col md:flex-row items-center gap-6 group hover:border-accent/40 transition-all">
                    <div className="flex-shrink-0 flex items-center justify-center h-16 w-16 bg-accent/10 rounded-2xl text-accent">
                        <svg className="w-8 h-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-black bg-accent text-bg px-1.5 py-0.5 rounded uppercase tracking-widest">Top Alpha Capture</span>
                            <span className="text-xs text-textMute">{topAlpha.game_label}</span>
                            <span className="text-xs text-textMute/50">•</span>
                            <span className="text-xs text-textMute">{new Date(topAlpha.captured_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                        </div>
                        <h3 className="text-xl font-bold text-textMain">
                            Captured {topAlpha.clv_prob ? (topAlpha.clv_prob * 100).toFixed(1) : "?"}% edge on {topAlpha.outcome} ({topAlpha.market})
                        </h3>
                        <p className="text-sm text-textMute mt-1">
                            Consensus moved from entry immediately after Stratum signal detection.
                        </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                        <div className="text-2xl font-black text-accent">{topAlpha.clv_prob ? `+${(topAlpha.clv_prob * 100).toFixed(1)}%` : "N/A"}</div>
                        <div className="text-[10px] text-textMute uppercase font-bold">CLV Improvement</div>
                    </div>
                </section>
            )}

            {/* Money Flow Heatmap Component */}
            {!loading && heatmap && (
                <section className="bg-panelSoft/80 border border-borderTone rounded-3xl p-6 relative overflow-hidden group">
                    <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-bg via-accent to-bg opacity-30 group-hover:opacity-100 transition-opacity" />
                    <div className="flex flex-col md:flex-row justify-between items-center gap-6 relative z-10">
                        <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="text-[10px] font-black bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded uppercase tracking-widest flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                    Smart Money Flow
                                </span>
                                <span className="text-xs font-semibold text-textMain">{heatmap.game_label}</span>
                                <span className="text-xs text-textMute/50">•</span>
                                <span className="text-xs text-textMute uppercase">{heatmap.market}</span>
                            </div>
                            <h3 className="text-2xl font-bold text-textMain">
                                {(heatmap.liquidity_asymmetry * 100).toFixed(0)}% <span className="text-textMute font-medium text-lg">of Exchange Liquidity on</span> {heatmap.outcome}
                            </h3>
                            <p className="text-sm text-textMute mt-1 max-w-xl">
                                Active prediction exchanges show a massive asymmetry. Sportsbooks have not fully adjusted the consensus line to match the flow of money.
                            </p>
                        </div>

                        <div className="flex flex-col gap-3 min-w-[240px] w-full md:w-auto bg-bg/50 p-4 rounded-2xl border border-white/5">
                            <div className="flex justify-between items-center">
                                <span className="text-xs text-textMute font-medium uppercase tracking-wider">Volume</span>
                                <span className="text-sm font-bold text-textMain">{heatmap.volume.toLocaleString()} contracts</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-xs text-textMute font-medium uppercase tracking-wider">Open Interest</span>
                                <span className="text-sm font-bold text-textMain">{heatmap.open_interest.toLocaleString()} active</span>
                            </div>

                            {/* Heatmap Bar */}
                            <div className="mt-2 h-3 w-full bg-bg rounded-full overflow-hidden flex relative">
                                <div className="absolute inset-0 bg-white/5" />
                                <div
                                    className="h-full bg-emerald-400 transition-all duration-1000 ease-out"
                                    style={{ width: `${heatmap.liquidity_asymmetry * 100}%` }}
                                />
                                <div
                                    className="h-full bg-rose-500/50 transition-all duration-1000 ease-out"
                                    style={{ width: `${(1 - heatmap.liquidity_asymmetry) * 100}%` }}
                                />
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {/* Grid of Insights */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Market Momentum Card */}
                <div className="p-6 bg-panel/40 backdrop-blur-sm border border-borderTone rounded-2xl hover:border-accent/30 transition-all group">
                    <div className="h-10 w-10 bg-accent/10 rounded-xl flex items-center justify-center text-accent mb-4 group-hover:scale-110 transition-transform">
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-bold">Market Momentum</h3>
                    <p className="text-sm text-textMute mt-2">
                        Track which books are moving first and where the market is converging.
                    </p>
                    <div className="mt-4 flex items-center justify-between">
                        <Link href="/app/dashboard" className="text-xs font-bold text-accent uppercase tracking-wider">
                            View Intel Feed
                        </Link>
                        <span className="text-[10px] font-bold text-textMute">{kpis?.books_tracked_estimate || "40+"} Books Tracked</span>
                    </div>
                </div>

                {/* Signal Integrity Card */}
                <div className="p-6 bg-panel/40 backdrop-blur-sm border border-borderTone rounded-2xl hover:border-accent/30 transition-all group">
                    <div className="h-10 w-10 bg-positive/10 rounded-xl flex items-center justify-center text-positive mb-4 group-hover:scale-110 transition-transform">
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-bold">Signal Performance</h3>
                    <p className="text-sm text-textMute mt-2">
                        Audit every signal against closing line value. Transparency is our edge.
                    </p>
                    <div className="mt-4 flex items-center justify-between">
                        <Link href="/app/performance" className="text-xs font-bold text-positive uppercase tracking-wider">
                            View Audit Log
                        </Link>
                        <div className="flex items-center gap-1">
                            <span className="h-1.5 w-1.5 rounded-full bg-positive" />
                            <span className="text-[10px] font-bold text-textMute">{kpis?.pct_actionable || "74"}% Success Rate</span>
                        </div>
                    </div>
                </div>

                {/* Watchlist Card */}
                <div className="p-6 bg-panel/40 backdrop-blur-sm border border-borderTone rounded-2xl hover:border-accent/30 transition-all group">
                    <div className="h-10 w-10 bg-primary/10 rounded-xl flex items-center justify-center text-primary mb-4 group-hover:scale-110 transition-transform">
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-bold">Your Focus</h3>
                    <p className="text-sm text-textMute mt-2">
                        Save specific games or markets to track volatility spikes personally.
                    </p>
                    <Link href="/app/watchlist" className="inline-block mt-4 text-xs font-bold text-primary uppercase tracking-wider">
                        Go to Watchlist
                    </Link>
                </div>
            </div>

            {/* Educational Promo Carousel Section */}
            <section className="bg-panelSoft/30 border border-borderTone rounded-3xl p-8 flex flex-col md:flex-row gap-8 items-center relative overflow-hidden transition-all duration-500 min-h-[250px]">
                <div className="flex-1 space-y-4 z-10 w-full">
                    <h2 className="text-2xl font-bold transition-opacity duration-500">{ARTICLES[activeArticleIdx].title}</h2>
                    <p className="text-textMute text-sm leading-relaxed transition-opacity duration-500">
                        {ARTICLES[activeArticleIdx].description}
                    </p>
                    <div className="flex gap-4 pt-2">
                        <Link href={ARTICLES[activeArticleIdx].link} className="px-4 py-2 bg-panel border border-borderTone rounded-lg text-xs font-bold hover:border-accent transition-colors">
                            {ARTICLES[activeArticleIdx].linkText}
                        </Link>
                    </div>
                </div>
                <div className="w-full md:w-64 aspect-square bg-bg rounded-2xl border border-borderTone/50 relative overflow-hidden flex items-center justify-center p-6 text-center z-10 transition-all duration-500">
                    <div className="absolute inset-0 bg-accent/5" />
                    <div className="relative space-y-2 w-full">
                        <div className="text-3xl font-bold text-accent">{ARTICLES[activeArticleIdx].stat}</div>
                        <div className="text-[10px] text-textMute uppercase tracking-widest font-bold">{ARTICLES[activeArticleIdx].statLabel}</div>
                        <div className="h-1 w-full bg-accent/20 rounded-full mt-2 overflow-hidden">
                            <div className={`h-full bg-accent transition-all duration-1000 ${ARTICLES[activeArticleIdx].statProgress}`} />
                        </div>
                    </div>
                </div>

                {/* Carousel Indicators */}
                <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-2 z-20">
                    {ARTICLES.map((_, idx) => (
                        <button
                            key={idx}
                            onClick={() => setActiveArticleIdx(idx)}
                            className={`h-1.5 rounded-full transition-all duration-300 ${activeArticleIdx === idx ? "w-6 bg-accent" : "w-1.5 bg-borderTone hover:bg-textMute"}`}
                            aria-label={`Go to slide ${idx + 1}`}
                        />
                    ))}
                </div>
            </section>
        </div>
    );
}
