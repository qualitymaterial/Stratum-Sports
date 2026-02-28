"use client";

import Link from "next/link";
import { useCurrentUser } from "@/lib/auth";
import { hasProAccess } from "@/lib/access";

export default function MarketOverviewPage() {
    const { user } = useCurrentUser(true);
    const isPro = hasProAccess(user);

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

                    {!isPro && (
                        <div className="mt-6 inline-flex items-center gap-4 bg-accent/5 border border-accent/20 px-4 py-2 rounded-full">
                            <span className="flex h-2 w-2 rounded-full bg-accent animate-pulse" />
                            <p className="text-xs font-semibold text-accent uppercase tracking-widest">
                                Watching Live Markets (10m Delay)
                            </p>
                            <Link href="/app/dashboard" className="text-xs font-bold text-textMain hover:underline ml-2">
                                Upgrade for Real-time →
                            </Link>
                        </div>
                    )}
                </div>
            </section>

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
                    <Link href="/app/dashboard" className="inline-block mt-4 text-xs font-bold text-accent uppercase tracking-wider">
                        View Intel Feed
                    </Link>
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
                    <Link href="/app/performance" className="inline-block mt-4 text-xs font-bold text-positive uppercase tracking-wider">
                        View Audit Log
                    </Link>
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

            {/* Educational Promo Section */}
            <section className="bg-panelSoft/30 border border-borderTone rounded-3xl p-8 flex flex-col md:flex-row gap-8 items-center">
                <div className="flex-1 space-y-4">
                    <h2 className="text-2xl font-bold">The Science of CLV</h2>
                    <p className="text-textMute text-sm leading-relaxed">
                        Unlike other platforms that focus on "win rates," Stratum focuses on **Closing Line Value (CLV)**.
                        If your entry price is consistently better than the market consensus at kick-off, you have a mathematical edge.
                        Our platform audits thousands of data points daily to ensure our signals capture this edge.
                    </p>
                    <div className="flex gap-4">
                        <Link href="/docs/signal-integrity" className="px-4 py-2 bg-panel border border-borderTone rounded-lg text-xs font-bold hover:border-accent transition-colors">
                            Read the Whitepaper
                        </Link>
                    </div>
                </div>
                <div className="w-full md:w-64 aspect-square bg-bg rounded-2xl border border-borderTone/50 relative overflow-hidden flex items-center justify-center p-6 text-center">
                    <div className="absolute inset-0 bg-accent/5" />
                    <div className="relative space-y-2">
                        <div className="text-3xl font-bold text-accent">+6.2%</div>
                        <div className="text-[10px] text-textMute uppercase tracking-widest font-bold">Avg Tier-S Alpha</div>
                        <div className="h-1 w-full bg-accent/20 rounded-full mt-2 overflow-hidden">
                            <div className="h-full bg-accent w-2/3" />
                        </div>
                    </div>
                </div>
            </section>
        </div>
    );
}
