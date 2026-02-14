"use client";

import { useTranslations } from "next-intl";
import { useState, useRef, useCallback } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
    Play,
    ClipboardPaste,
    Loader2,
    CheckCircle2,
    XCircle,
    SkipForward,
    StopCircle,
    FileJson,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8046/api";

type ImportPhase = "select" | "preview" | "importing" | "done";

interface ImportResult {
    success: number;
    skipped: number;
    failed: number;
    errors: string[];
}

interface ImportDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    clientType: "gemini_cli" | "antigravity";
    onComplete?: () => void;
}

export function ImportDialog({ open, onOpenChange, clientType, onComplete }: ImportDialogProps) {
    const t = useTranslations("accounts");
    const [phase, setPhase] = useState<ImportPhase>("select");
    const [pasteMode, setPasteMode] = useState(false);
    const [pasteContent, setPasteContent] = useState("");
    const [parsedAccounts, setParsedAccounts] = useState<any[]>([]);
    const [parseError, setParseError] = useState("");
    const [progress, setProgress] = useState({ current: 0, total: 0 });
    const [result, setResult] = useState<ImportResult | null>(null);
    const abortRef = useRef(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const reset = useCallback(() => {
        setPhase("select");
        setPasteMode(false);
        setPasteContent("");
        setParsedAccounts([]);
        setParseError("");
        setProgress({ current: 0, total: 0 });
        setResult(null);
        abortRef.current = false;
    }, []);

    const handleOpenChange = (next: boolean) => {
        if (!next && phase === "importing") {
            // Can't close during import
            return;
        }
        if (!next) {
            reset();
        }
        onOpenChange(next);
    };

    const parseJson = (content: string) => {
        try {
            let data = JSON.parse(content);

            // Normalize: if it's an object with "accounts" key, extract it
            if (data && !Array.isArray(data) && Array.isArray(data.accounts)) {
                data = data.accounts;
            }

            if (!Array.isArray(data) || data.length === 0) {
                setParseError(t("importInvalidFormat"));
                return;
            }

            // Normalize each entry
            const normalized = data.map((item: any) => {
                // Simple format: { email, refresh_token }
                if (item.refresh_token && !item.credentials) {
                    return {
                        email: item.email || "",
                        credentials: [
                            { client_type: clientType, refresh_token: item.refresh_token }
                        ],
                    };
                }
                // Full format: { email, credentials: [...] }
                if (item.credentials && Array.isArray(item.credentials)) {
                    return {
                        email: item.email || "",
                        credentials: item.credentials,
                        device_profile: item.device_profile,
                    };
                }
                return null;
            }).filter(Boolean);

            if (normalized.length === 0) {
                setParseError(t("importInvalidFormat"));
                return;
            }

            setParsedAccounts(normalized);
            setParseError("");
            setPhase("preview");
        } catch {
            setParseError(t("importInvalidFormat"));
        }
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
            const content = await file.text();
            parseJson(content);
        } catch {
            setParseError(t("importInvalidFormat"));
        } finally {
            e.target.value = "";
        }
    };

    const handlePasteConfirm = () => {
        if (!pasteContent.trim()) return;
        parseJson(pasteContent);
    };

    const startImport = async () => {
        setPhase("importing");
        abortRef.current = false;

        const total = parsedAccounts.length;
        setProgress({ current: 0, total });

        let success = 0;
        let skipped = 0;
        let failed = 0;
        const errors: string[] = [];

        for (let i = 0; i < total; i++) {
            if (abortRef.current) break;

            const acct = parsedAccounts[i];
            try {
                const res = await fetch(`${API_BASE}/accounts/import`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ accounts: [acct] }),
                });
                const data = await res.json();
                success += data.success || 0;
                skipped += data.skipped || 0;
                failed += data.failed || 0;
                if (data.errors?.length) {
                    errors.push(...data.errors);
                }
            } catch (err) {
                failed++;
                errors.push(`${acct.email || "unknown"}: Network error`);
            }

            setProgress({ current: i + 1, total });
            // Small delay between imports
            await new Promise(r => setTimeout(r, 80));
        }

        setResult({ success, skipped, failed, errors });
        setPhase("done");
        onComplete?.();
    };

    const handleAbort = () => {
        abortRef.current = true;
    };

    const pct = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent
                className="sm:max-w-lg"
                onInteractOutside={(e) => { if (phase === "importing") e.preventDefault(); }}
                onEscapeKeyDown={(e) => { if (phase === "importing") e.preventDefault(); }}
            >
                <DialogHeader>
                    <DialogTitle>{t("importTitle")}</DialogTitle>
                    <DialogDescription>
                        {phase === "select" && t("importDesc")}
                        {phase === "preview" && t("importPreviewDesc", { count: parsedAccounts.length })}
                        {phase === "importing" && t("importingDesc")}
                        {phase === "done" && t("importDoneDesc")}
                    </DialogDescription>
                </DialogHeader>

                {/* Phase: Select source */}
                {phase === "select" && !pasteMode && (
                    <div className="space-y-3">
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".json,application/json"
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                        <button
                            className="flex w-full items-center gap-3 rounded-lg border border-border p-4 text-left transition-colors hover:bg-accent/5"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                                <FileJson className="h-5 w-5" />
                            </div>
                            <div>
                                <div className="text-sm font-medium">{t("importFromFile")}</div>
                                <div className="text-xs text-muted-foreground">{t("importFromFileDesc")}</div>
                            </div>
                        </button>
                        <button
                            className="flex w-full items-center gap-3 rounded-lg border border-border p-4 text-left transition-colors hover:bg-accent/5"
                            onClick={() => setPasteMode(true)}
                        >
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                                <ClipboardPaste className="h-5 w-5" />
                            </div>
                            <div>
                                <div className="text-sm font-medium">{t("importFromPaste")}</div>
                                <div className="text-xs text-muted-foreground">{t("importFromPasteDesc")}</div>
                            </div>
                        </button>
                        {parseError && (
                            <div className="rounded-md bg-destructive/10 p-3 text-xs text-destructive">
                                {parseError}
                            </div>
                        )}
                    </div>
                )}

                {/* Phase: Paste mode */}
                {phase === "select" && pasteMode && (
                    <div className="space-y-3">
                        <textarea
                            className="w-full h-48 rounded-lg border border-border bg-muted/30 p-3 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                            placeholder={t("importPastePlaceholder")}
                            value={pasteContent}
                            onChange={(e) => setPasteContent(e.target.value)}
                            autoFocus
                        />
                        {parseError && (
                            <div className="rounded-md bg-destructive/10 p-3 text-xs text-destructive">
                                {parseError}
                            </div>
                        )}
                        <div className="flex items-center justify-end gap-2">
                            <Button variant="outline" size="sm" className="text-xs" onClick={() => { setPasteMode(false); setParseError(""); }}>
                                {t("importBack")}
                            </Button>
                            <Button size="sm" className="text-xs gap-1.5" onClick={handlePasteConfirm} disabled={!pasteContent.trim()}>
                                <Play className="h-3.5 w-3.5" />
                                {t("importParse")}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Phase: Preview */}
                {phase === "preview" && (
                    <div className="space-y-3">
                        <div className="max-h-48 overflow-auto rounded-lg border border-border divide-y divide-border">
                            {parsedAccounts.map((acct, i) => (
                                <div key={i} className="flex items-center gap-3 px-3 py-2 text-xs">
                                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                                        {i + 1}
                                    </div>
                                    <span className="font-medium truncate flex-1">{acct.email || t("importUnknownEmail")}</span>
                                    <span className="text-muted-foreground shrink-0">
                                        {(acct.credentials || []).map((c: any) => c.client_type).join(", ")}
                                    </span>
                                </div>
                            ))}
                        </div>
                        <div className="flex items-center justify-end gap-2">
                            <Button variant="outline" size="sm" className="text-xs" onClick={reset}>
                                {t("importBack")}
                            </Button>
                            <Button size="sm" className="text-xs gap-1.5" onClick={startImport}>
                                <Play className="h-3.5 w-3.5" />
                                {t("importStart", { count: parsedAccounts.length })}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Phase: Importing */}
                {phase === "importing" && (
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <span>{t("importProgress", { current: progress.current, total: progress.total })}</span>
                                <span>{pct}%</span>
                            </div>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                                <div
                                    className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                        </div>
                        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            {t("importingLabel")}
                        </div>
                        <div className="flex items-center justify-center">
                            <Button
                                variant="destructive"
                                size="sm"
                                className="text-xs gap-1.5"
                                onClick={handleAbort}
                            >
                                <StopCircle className="h-3.5 w-3.5" />
                                {t("importAbort")}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Phase: Done */}
                {phase === "done" && result && (
                    <div className="space-y-4 py-2">
                        <div className="flex items-center justify-center gap-6 text-sm">
                            <div className="flex flex-col items-center gap-1">
                                <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                                    <CheckCircle2 className="h-4 w-4" />
                                    <span className="font-semibold">{result.success}</span>
                                </div>
                                <span className="text-[11px] text-muted-foreground">{t("importSuccess")}</span>
                            </div>
                            <div className="flex flex-col items-center gap-1">
                                <div className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                                    <SkipForward className="h-4 w-4" />
                                    <span className="font-semibold">{result.skipped}</span>
                                </div>
                                <span className="text-[11px] text-muted-foreground">{t("importSkipped")}</span>
                            </div>
                            <div className="flex flex-col items-center gap-1">
                                <div className="flex items-center gap-1 text-red-600 dark:text-red-400">
                                    <XCircle className="h-4 w-4" />
                                    <span className="font-semibold">{result.failed}</span>
                                </div>
                                <span className="text-[11px] text-muted-foreground">{t("importFailed")}</span>
                            </div>
                        </div>
                        {result.errors.length > 0 && (
                            <div className="max-h-24 overflow-auto rounded-md bg-destructive/5 p-3 text-xs text-destructive space-y-1">
                                {result.errors.map((err, i) => (
                                    <div key={i}>• {err}</div>
                                ))}
                            </div>
                        )}
                        <div className="flex items-center justify-center">
                            <Button size="sm" className="text-xs" onClick={() => handleOpenChange(false)}>
                                {t("importClose")}
                            </Button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
