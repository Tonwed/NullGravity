"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";

const API_BASE = "http://127.0.0.1:8046/api";
import { useWebSocket } from "./websocket-provider";



export interface LogEntry {
    id: number;
    timestamp: string;
    method: string;
    path: string;
    status_code: number;
    duration_ms: number;
    client_ip: string | null;
    request_headers: Record<string, any> | null;
    request_body: string | null;
    response_body: string | null;
    error_detail: string | null;
    account: {
        id: string;
        email: string;
        avatar_url: string | null;
        display_name: string | null;
    } | null;
}

interface LogContextType {
    logs: LogEntry[];
    loading: boolean;
    refresh: () => Promise<void>;
    clear: () => Promise<void>;
}

const LogContext = createContext<LogContextType | null>(null);

export function LogProvider({ children }: { children: ReactNode }) {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/logs/?page=1&page_size=100`);
            if (res.ok) {
                const data = await res.json();
                setLogs(data.items);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, []);

    const clear = useCallback(async () => {
        try {
            await fetch(`${API_BASE}/logs/`, { method: "DELETE" });
            fetchLogs();
        } catch { }
    }, [fetchLogs]);

    const { subscribe } = useWebSocket();



    useEffect(() => {
        // Initial load
        fetchLogs();

        const unsubscribe = subscribe((data: any) => {
            console.log("LogProvider received:", data);
            if (data && data.type === "log" && data.payload) {
                const log: LogEntry = data.payload;
                setLogs(prev => {
                    // Deduplicate
                    if (prev.some(p => p.id === log.id)) return prev;
                    // Prepend new log and keep limit
                    return [log, ...prev].slice(0, 100);
                });
            }
        });

        return unsubscribe;
    }, [fetchLogs, subscribe]);

    return (
        <LogContext.Provider value={{ logs, loading, refresh: fetchLogs, clear }}>
            {children}
        </LogContext.Provider>
    );
}

export const useLogs = () => {
    const context = useContext(LogContext);
    if (!context) throw new Error("useLogs must be used within LogProvider");
    return context;
};
