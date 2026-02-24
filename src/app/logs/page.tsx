"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
    FileText,
    Trash2,
    ChevronRight,
    ChevronDown,
    RefreshCcw,
    Inbox
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { useLogs } from "@/components/providers/log-provider";

export default function LogsPage() {
    const t = useTranslations("logs");
    const { logs, loading, refresh, clear } = useLogs();
    const [page, setPage] = useState(1);
    const [expandedId, setExpandedId] = useState<number | null>(null);

    // Client-side pagination
    const pageSize = 50;
    const totalPages = Math.max(1, Math.ceil(logs.length / pageSize));
    const displayLogs = logs.slice((page - 1) * pageSize, page * pageSize);

    const handleClear = async () => {
        if (!confirm(t("confirmClear"))) return;
        await clear();
    };

    const toggleExpand = (id: number) => {
        setExpandedId(prev => (prev === id ? null : id));
    };

    // Helper for JSON pretty print
    const formatBody = (body: string | null) => {
        if (!body) return <span className="text-muted-foreground italic">Empty</span>;
        try {
            const obj = JSON.parse(body);
            return <pre className="text-xs font-mono whitespace-pre-wrap">{JSON.stringify(obj, null, 2)}</pre>;
        } catch {
            return <pre className="text-xs font-mono whitespace-pre-wrap">{body}</pre>;
        }
    };

    return (
        <div className="mx-auto w-full max-w-7xl flex-1 flex flex-col space-y-5 animate-in fade-in duration-500">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold">{t("title")}</h1>
                    <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => refresh()} disabled={loading} className="gap-1.5 h-8 text-xs">
                        <RefreshCcw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                        Refresh
                    </Button>
                    <Button variant="destructive" size="sm" onClick={handleClear} className="gap-1.5 h-8 text-xs">
                        <Trash2 className="h-3.5 w-3.5" />
                        Clear
                    </Button>
                </div>
            </div>

            {/* Table Container */}
            <div className="rounded-lg border border-border bg-card overflow-hidden text-xs shadow-sm">
                {/* Table Header */}
                <div className="grid grid-cols-[30px_180px_60px_1fr_60px_140px_60px] gap-4 border-b border-border px-4 py-2 font-medium text-muted-foreground uppercase tracking-wider text-[11px] bg-card">
                    <div></div>
                    <div>Account</div>
                    <div>{t("method")}</div>
                    <div>{t("path")}</div>
                    <div>{t("status")}</div>
                    <div>{t("timestamp")}</div>
                    <div className="text-right">{t("duration")}</div>
                </div>

                {/* Table Body */}
                <div className="divide-y divide-border/60 bg-card">
                    {!loading && logs.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                            <Inbox className="h-8 w-8 text-muted-foreground/40 mb-3" />
                            <p className="text-sm font-medium">No logs recorded</p>
                            <p className="text-xs text-muted-foreground/70 mt-1">External API requests will appear here</p>
                            <p className="text-[10px] text-muted-foreground/50 mt-1">(Real-time updates enabled)</p>
                        </div>
                    )}

                    {displayLogs.map((log) => (
                        <div key={log.id} className="group transition-colors">
                            {/* Row */}
                            <div
                                className={cn(
                                    "grid grid-cols-[30px_180px_60px_1fr_60px_140px_60px] gap-4 px-4 py-2.5 items-center hover:bg-muted/40 transition-colors cursor-pointer border-l-2 border-l-transparent",
                                    expandedId === log.id ? "bg-muted/40 border-l-primary" : "hover:border-l-muted-foreground/30"
                                )}
                                onClick={() => toggleExpand(log.id)}
                            >
                                <div className="flex justify-center">
                                    {expandedId === log.id ? (
                                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                                    ) : (
                                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground" />
                                    )}
                                </div>
                                <div className="flex items-center gap-2 overflow-hidden">
                                    {log.account ? (
                                        <>
                                            <Avatar className="h-5 w-5">
                                                <AvatarImage src={`http://127.0.0.1:8046/api/accounts/${log.account.id}/avatar`} />
                                                <AvatarFallback>{log.account.email[0].toUpperCase()}</AvatarFallback>
                                            </Avatar>
                                            <div className="truncate text-[10px] text-muted-foreground" title={log.account.email}>
                                                {log.account.email}
                                            </div>
                                        </>
                                    ) : (
                                        <span className="text-[10px] text-muted-foreground/40 italic">Anonymous</span>
                                    )}
                                </div>
                                <div>
                                    <Badge variant="outline" className={cn(
                                        "font-mono text-[9px] uppercase font-bold px-1.5 py-0 h-5",
                                        log.method === "GET" && "text-blue-500 border-blue-500/20 bg-blue-500/5",
                                        log.method === "POST" && "text-emerald-500 border-emerald-500/20 bg-emerald-500/5",
                                        log.method === "DELETE" && "text-red-500 border-red-500/20 bg-red-500/5",
                                        log.method === "PATCH" && "text-amber-500 border-amber-500/20 bg-amber-500/5"
                                    )}>
                                        {log.method}
                                    </Badge>
                                </div>
                                <div className="font-mono text-[11px] truncate text-foreground/90" title={log.path}>
                                    {log.path}
                                </div>
                                <div>
                                    <Badge
                                        variant="outline"
                                        className={cn(
                                            "font-mono text-[9px] px-1.5 py-0 h-5",
                                            log.status_code >= 200 && log.status_code < 300 && "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
                                            log.status_code >= 400 && "bg-destructive/10 text-destructive border-destructive/20"
                                        )}
                                    >
                                        {log.status_code}
                                    </Badge>
                                </div>
                                <div className="font-mono text-[11px] text-muted-foreground/80">
                                    {new Date(log.timestamp).toLocaleString()}
                                </div>
                                <div className="text-right font-mono text-[11px] text-muted-foreground">
                                    {log.duration_ms.toFixed(0)}ms
                                </div>
                            </div>

                            {/* Expanded Detail */}
                            {expandedId === log.id && (
                                <div className="bg-card border-b border-border/60 px-4 py-4 animate-in slide-in-from-top-1 duration-200">
                                    <div className="grid grid-cols-2 gap-4">
                                        {/* Request Section */}
                                        <div className="space-y-2 border rounded-md p-3 bg-background/60">
                                            <h3 className="font-semibold text-xs flex items-center gap-2">
                                                <span className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[10px] uppercase font-bold">REQ</span>
                                                {t("request")} Details
                                            </h3>
                                            <div>
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">{t("headers")}</div>
                                                <div className="max-h-24 overflow-auto rounded border bg-muted/30 w-full">
                                                    <div className="p-2 font-mono text-[10px]">
                                                        {JSON.stringify(log.request_headers, null, 2)}
                                                    </div>
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">{t("body")}</div>
                                                <div className="max-h-32 overflow-auto rounded border bg-muted/30 w-full">
                                                    <div className="p-2 font-mono text-[10px] break-all">
                                                        {formatBody(log.request_body)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Response Section */}
                                        <div className="space-y-2 border rounded-md p-3 bg-background/60">
                                            <h3 className="font-semibold text-xs flex items-center gap-2">
                                                <span className={cn(
                                                    "px-1.5 py-0.5 rounded text-[10px] uppercase font-bold",
                                                    log.status_code >= 400 ? "bg-destructive/10 text-destructive" : "bg-emerald-500/10 text-emerald-600"
                                                )}>RES</span>
                                                {t("response")} Details
                                            </h3>
                                            {log.error_detail && (
                                                <div className="bg-destructive/10 text-destructive p-2 rounded text-[10px] font-mono mb-2 border border-destructive/20">
                                                    <span className="font-bold">Error:</span> {log.error_detail}
                                                </div>
                                            )}
                                            <div>
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">{t("body")}</div>
                                                <div className="max-h-64 overflow-auto rounded border bg-muted/30 w-full">
                                                    <div className="p-2 font-mono text-[10px] break-all">
                                                        {formatBody(log.response_body)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>

                {/* Pagination */}
                <div className="p-2 border-t border-border flex justify-between items-center text-[10px] px-4 bg-muted/20">
                    <span className="text-muted-foreground">
                        Page {page} of {totalPages}
                    </span>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page <= 1}
                        >
                            <ChevronDown className="h-3.5 w-3.5 rotate-90" />
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                        >
                            <ChevronRight className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                </div>
            </div>
        </div >
    );
}
