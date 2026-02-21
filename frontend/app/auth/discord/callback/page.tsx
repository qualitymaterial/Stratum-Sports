"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { LoadingState } from "@/components/LoadingState";
import { discordCallback } from "@/lib/api";
import { setSession } from "@/lib/auth";

function CallbackContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const code = searchParams.get("code");
        if (!code) {
            setError("No code provided from Discord");
            return;
        }

        void discordCallback(code)
            .then((result) => {
                setSession(result.access_token, result.user);
                router.replace("/app/dashboard");
            })
            .catch((err) => {
                setError(err instanceof Error ? err.message : "Discord login failed");
            });
    }, [searchParams, router]);

    if (error) {
        return (
            <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
                <div className="w-full rounded-2xl border border-borderTone bg-panel p-8 shadow-terminal">
                    <h1 className="text-xl font-semibold text-negative">Authentication Error</h1>
                    <p className="mt-4 text-sm text-textMute">{error}</p>
                    <button
                        onClick={() => router.replace("/login")}
                        className="mt-6 w-full rounded-md border border-borderTone py-2 text-sm text-textMain hover:bg-panelSoft"
                    >
                        Back to Login
                    </button>
                </div>
            </main>
        );
    }

    return <LoadingState label="Completing Discord login..." />;
}

export default function DiscordCallbackPage() {
    return (
        <Suspense fallback={<LoadingState label="Authenticating..." />}>
            <CallbackContent />
        </Suspense>
    );
}
