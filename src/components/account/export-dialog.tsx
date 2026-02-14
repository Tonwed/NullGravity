"use client";

import { useTranslations } from "next-intl";
import { useState, useEffect, useCallback } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Copy, Download, Check, Loader2 } from "lucide-react";

const API_BASE = "http://127.0.0.1:8046/api";

interface ExportDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    accountIds?: string[];
}

export function ExportDialog({ open, onOpenChange, accountIds }: ExportDialogProps) {
    const t = useTranslations("accounts");
    const [json, setJson] = useState("");
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);

    const fetchExportData = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/accounts/export`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ account_ids: accountIds || [] }),
            });
            const data = await res.json();

            // Export all credentials for each account (no client type filtering)
            const accounts = (data.accounts || []).filter(
                (acct: any) => (acct.credentials || []).length > 0
            );

            setJson(JSON.stringify(accounts, null, 2));
        } catch {
            setJson("[]");
        } finally {
            setLoading(false);
        }
    }, [accountIds]);

    useEffect(() => {
        if (open) {
            fetchExportData();
            setCopied(false);
        }
    }, [open, fetchExportData]);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(json);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // fallback
            const ta = document.createElement("textarea");
            ta.value = json;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const handleSaveFile = () => {
        const blob = new Blob([json], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `nullgravity_export_${new Date().toISOString().split("T")[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // Count accounts
    let accountCount = 0;
    try {
        accountCount = JSON.parse(json).length;
    } catch { /* ignore */ }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl w-[calc(100vw-2rem)]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {t("exportTitle")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("exportDesc", { count: accountCount })}
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <>
                        <div className="relative min-w-0">
                            <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-muted/30 p-3 text-xs font-mono leading-relaxed text-foreground/90 select-all whitespace-pre-wrap break-all">
                                {json}
                            </pre>
                        </div>

                        <div className="flex items-center justify-end gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                className="gap-1.5 text-xs"
                                onClick={handleCopy}
                            >
                                {copied ? (
                                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                                ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                )}
                                {copied ? t("exportCopied") : t("exportCopy")}
                            </Button>
                            <Button
                                size="sm"
                                className="gap-1.5 text-xs"
                                onClick={handleSaveFile}
                            >
                                <Download className="h-3.5 w-3.5" />
                                {t("exportSaveFile")}
                            </Button>
                        </div>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
}
