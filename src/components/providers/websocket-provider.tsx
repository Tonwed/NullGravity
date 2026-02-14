"use client";

import { createContext, useContext, useEffect, useState, ReactNode, useCallback, useMemo } from "react";

const API_BASE = "http://127.0.0.1:8046/api";
const WS_URL = API_BASE.replace("http", "ws") + "/ws";

interface WebSocketContextType {
    lastMessage: any;
    isConnected: boolean;
    subscribe: (callback: (msg: any) => void) => () => void;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
    const [lastMessage, setLastMessage] = useState<any>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [retryCount, setRetryCount] = useState(0);
    const [listeners] = useState(() => new Set<(msg: any) => void>());

    useEffect(() => {
        let ws: WebSocket | null = null;
        let pingInterval: NodeJS.Timeout;

        const connect = () => {
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                console.log("Global WS Connected");
                setIsConnected(true);
                setRetryCount(0);
                pingInterval = setInterval(() => {
                    if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
                }, 30000);
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    setLastMessage(data);
                    listeners.forEach(l => {
                        try { l(data); } catch (e) { console.error("Listener error", e); }
                    });
                } catch (e) {
                    console.error("WS Parse Error", e);
                }
            };

            ws.onclose = () => {
                console.log("Global WS Closed");
                setIsConnected(false);
                setTimeout(() => setRetryCount(pk => pk + 1), Math.min(1000 * (retryCount + 1), 5000));
            };
        };

        connect();

        return () => {
            if (pingInterval) clearInterval(pingInterval);
            if (ws) {
                ws.onclose = null;
                ws.close();
            }
        };
    }, [retryCount]);

    const subscribe = useCallback((cb: (msg: any) => void) => {
        listeners.add(cb);
        return () => { listeners.delete(cb); };
    }, [listeners]);

    const value = useMemo(() => ({
        lastMessage,
        isConnected,
        subscribe
    }), [lastMessage, isConnected, subscribe]);

    return (
        <WebSocketContext.Provider value={value}>
            {children}
        </WebSocketContext.Provider>
    );
}

export const useWebSocket = () => {
    const context = useContext(WebSocketContext);
    if (!context) throw new Error("useWebSocket must be used within WebSocketProvider");
    return context;
};
