"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type WebSocketMessage = {
    type: "odds_update";
    event_id: string;
    sportsbook: string;
    market: string;
    outcome: string;
    line: number | null;
    price: number;
    timestamp: string;
};

function buildWebSocketUrl(): string {
    try {
        const apiUrl = new URL(API_BASE);
        const protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${apiUrl.host}/api/v1/realtime/odds`;
    } catch {
        return "ws://localhost:8000/api/v1/realtime/odds";
    }
}

export function useOddsSocket(onMessage: (msg: WebSocketMessage) => void) {
    const socketRef = useRef<WebSocket | null>(null);
    const [connected, setConnected] = useState(false);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
    const blockedReconnectRef = useRef(false);

    const connect = useCallback(() => {
        if (blockedReconnectRef.current) return;

        const token = getToken();
        if (!token) return;

        const wsUrl = buildWebSocketUrl();
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            ws.send(JSON.stringify({ type: "auth", token }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data) as WebSocketMessage | { type: "auth_ok" };
                if (data.type === "auth_ok") {
                    setConnected(true);
                    return;
                }
                onMessage(data);
            } catch {
                console.error("Failed to parse WebSocket message");
            }
        };

        ws.onclose = (event) => {
            setConnected(false);
            if (event.code === 1008) {
                blockedReconnectRef.current = true;
                return;
            }
            // Attempt to reconnect after 3 seconds
            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 3000);
        };

        ws.onerror = () => {
            console.error("Odds WebSocket error");
            ws.close();
        };

        socketRef.current = ws;
    }, [onMessage]);

    useEffect(() => {
        blockedReconnectRef.current = false;
        connect();
        return () => {
            if (socketRef.current) {
                socketRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            blockedReconnectRef.current = true;
        };
    }, [connect]);

    return { connected };
}
