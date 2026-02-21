"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";

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

export function useOddsSocket(onMessage: (msg: WebSocketMessage) => void) {
    const socketRef = useRef<WebSocket | null>(null);
    const [connected, setConnected] = useState(false);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout>();

    const connect = useCallback(() => {
        const token = getToken();
        if (!token) return;

        const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
        const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
        const wsUrl = `${wsProtocol}://${host}:8000/api/v1/realtime/odds?token=${encodeURIComponent(token)}`;

        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setConnected(true);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data) as WebSocketMessage;
                onMessage(data);
            } catch (err) {
                console.error("Failed to parse WebSocket message", err);
            }
        };

        ws.onclose = () => {
            setConnected(false);
            // Attempt to reconnect after 3 seconds
            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 3000);
        };

        ws.onerror = (err) => {
            console.error("Odds WebSocket error");
            ws.close();
        };

        socketRef.current = ws;
    }, [onMessage]);

    useEffect(() => {
        connect();
        return () => {
            if (socketRef.current) {
                socketRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
    }, [connect]);

    return { connected };
}
