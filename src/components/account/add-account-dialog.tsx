"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslations } from "next-intl";
import {
    ExternalLink,
    Copy,
    Check,
    Loader2,
    AlertCircle,
    CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

const API_BASE = "http://127.0.0.1:8046/api";
const POLL_INTERVAL = 2000; // ms
const AUTH_TIMEOUT = 5 * 60 * 1000; // 5 minutes

type AuthStep = "idle" | "authenticating" | "setting_up" | "success" | "error";

interface AddAccountDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onAccountAdded?: () => void;
    targetEmail?: string;
}

export function AddAccountDialog({
    open,
    onOpenChange,
    onAccountAdded,
    targetEmail,
}: AddAccountDialogProps) {
    const t = useTranslations("accounts");
    const [step, setStep] = useState<AuthStep>("idle");
    const [authUrl, setAuthUrl] = useState("");
    const [sessionId, setSessionId] = useState("");
    const [copied, setCopied] = useState(false);
    const [error, setError] = useState("");
    const [addedEmail, setAddedEmail] = useState("");
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Cleanup polling on unmount or dialog close
    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (!open) {
            // Reset state when dialog closes
            setTimeout(() => {
                setStep("idle");
                setAuthUrl("");
                setSessionId("");
                setCopied(false);
                setError("");
                setAddedEmail("");
                stopPolling();
            }, 200);
        } else {
            if (targetEmail) setAddedEmail(targetEmail);
        }
    }, [open, stopPolling, targetEmail]);

    useEffect(() => {
        return stopPolling;
    }, [stopPolling]);

    // Start Antigravity OAuth flow
    const startAuth = useCallback(async () => {
        setStep("authenticating");
        setError("");

        try {
            const res = await fetch(`${API_BASE}/auth/google/start?client_type=antigravity`, {
                method: "POST",
            });

            if (!res.ok) {
                throw new Error(`Server returned ${res.status}`);
            }

            const data = await res.json();
            setAuthUrl(data.auth_url);
            setSessionId(data.session_id);

            // Set a 5-minute timeout to give up
            timeoutRef.current = setTimeout(() => {
                stopPolling();
                setError("Authentication timed out. Please try again.");
                setStep("error");
            }, AUTH_TIMEOUT);

            // Start polling for auth status
            pollRef.current = setInterval(async () => {
                try {
                    const statusRes = await fetch(
                        `${API_BASE}/auth/google/status/${data.session_id}`
                    );
                    const statusData = await statusRes.json();

                    if (statusData.status === "success") {
                        const newEmail = statusData.email || "";
                        const expected = targetEmail || addedEmail;

                        if (newEmail && expected && newEmail !== expected) {
                            stopPolling();
                            setError(`Expected account ${expected}, but logged in as ${newEmail}. Please use the correct account.`);
                            setStep("error");
                            return;
                        }

                        stopPolling();
                        setAddedEmail(newEmail);
                        setStep("setting_up");

                        // Trigger setup (fetch user data)
                        if (statusData.account_id) {
                            try {
                                await fetch(`${API_BASE}/auth/google/setup/${statusData.account_id}`, { method: "POST" });
                            } catch (e) {
                                console.error("Setup failed after auth", e);
                            }
                        }

                        await new Promise(r => setTimeout(r, 800));
                        setStep("success");
                        onAccountAdded?.();
                    } else if (statusData.status === "error") {
                        stopPolling();
                        setError(statusData.error || "Unknown error");
                        setStep("error");
                    }
                } catch {
                    // Ignore poll errors
                }
            }, POLL_INTERVAL);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to start auth");
            setStep("error");
        }
    }, [onAccountAdded, stopPolling, targetEmail, addedEmail]);

    // Copy auth URL to clipboard
    const copyToClipboard = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(authUrl);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Fallback
        }
    }, [authUrl]);

    // Open URL in browser
    const openInBrowser = useCallback(() => {
        window.open(authUrl, "_blank");
    }, [authUrl]);

    const getDescription = () => {
        switch (step) {
            case "authenticating":
                return "正在连接 Antigravity 客户端";
            case "setting_up":
                return "正在同步 Antigravity 数据";
            default:
                return "通过 Antigravity 登录 Google 账号以获取 API 额度与模型权限";
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[440px]" onInteractOutside={(e) => e.preventDefault()}>
                <DialogHeader>
                    <DialogTitle className="text-base">{t("addAccountTitle")}</DialogTitle>
                    <DialogDescription className="text-xs">
                        {getDescription()}
                    </DialogDescription>
                </DialogHeader>

                <div className="mt-4">
                    {/* Idle: Show login button */}
                    {step === "idle" && (
                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div className="grid grid-cols-1 gap-3">
                                <button
                                    onClick={startAuth}
                                    className="flex w-full items-center gap-4 rounded-xl border border-border bg-card p-4 transition-all hover:bg-accent hover:border-primary/20 hover:shadow-sm group relative overflow-hidden text-left"
                                >
                                    <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

                                    <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-500/10 group-hover:scale-105 transition-transform">
                                        <img
                                            src="/antigravity-logo.png"
                                            alt="Antigravity"
                                            className="h-7 w-7 object-contain"
                                        />
                                    </div>

                                    <div className="flex-1 min-w-0 z-10 space-y-1">
                                        <div className="flex items-center justify-between">
                                            <span className="font-semibold text-sm">Antigravity 登录</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground leading-relaxed">
                                            通过 Google 账号登录，获取 API 额度、模型权限与代码助手功能。
                                        </p>
                                    </div>
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Setting up */}
                    {step === "setting_up" && (
                        <div className="flex flex-col items-center justify-center py-8 gap-4 animate-in fade-in zoom-in-95 duration-300">
                            <div className="relative">
                                <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full animate-pulse" />
                                <Loader2 className="relative h-10 w-10 animate-spin text-primary" />
                            </div>
                            <div className="text-center space-y-1.5">
                                <p className="text-sm font-semibold">认证成功</p>
                                <p className="text-xs text-muted-foreground">
                                    正在获取 Antigravity 模型与额度信息...
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Authenticating */}
                    {step === "authenticating" && (
                        <div className="space-y-6 animate-in fade-in zoom-in-95 duration-300">
                            <div className="flex flex-col items-center gap-4 py-4">
                                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/10">
                                    <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                                    <div className="absolute inset-0 rounded-full animate-ping opacity-20 bg-blue-500" />
                                </div>
                                <div className="text-center space-y-1">
                                    <p className="text-sm font-semibold">
                                        正在连接 Antigravity...
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        请在新打开的浏览器窗口中完成 Google 授权
                                    </p>
                                </div>
                            </div>

                            {authUrl && (
                                <div className="space-y-3">
                                    <div className="rounded-lg bg-muted/50 p-3 border border-border/50">
                                        <p className="text-[10px] text-muted-foreground break-all line-clamp-2 font-mono leading-relaxed opacity-70">
                                            {authUrl}
                                        </p>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-9 gap-2 text-xs"
                                            onClick={openInBrowser}
                                        >
                                            <ExternalLink className="h-3.5 w-3.5" />
                                            {t("openInBrowser")}
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-9 gap-2 text-xs"
                                            onClick={copyToClipboard}
                                        >
                                            {copied ? (
                                                <Check className="h-3.5 w-3.5 text-emerald-500" />
                                            ) : (
                                                <Copy className="h-3.5 w-3.5" />
                                            )}
                                            {copied ? t("copied") : t("copyLink")}
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Success */}
                    {step === "success" && (
                        <div className="flex flex-col items-center gap-4 py-8 animate-in fade-in zoom-in-95 duration-300">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
                                <CheckCircle2 className="h-8 w-8 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <div className="text-center space-y-1">
                                <p className="text-base font-semibold">{t("authSuccess")}</p>
                                {addedEmail && (
                                    <p className="text-sm text-muted-foreground">{addedEmail}</p>
                                )}
                            </div>
                            <Button
                                size="sm"
                                className="mt-4 px-6"
                                onClick={() => onOpenChange(false)}
                            >
                                {t("close")}
                            </Button>
                        </div>
                    )}

                    {/* Error */}
                    {step === "error" && (
                        <div className="flex flex-col items-center gap-4 py-6 animate-in fade-in zoom-in-95 duration-300">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
                                <AlertCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
                            </div>
                            <div className="text-center space-y-1">
                                <p className="text-base font-semibold">{t("authError")}</p>
                                {error && (
                                    <p className="text-xs text-muted-foreground opacity-80 max-w-[320px] mx-auto">
                                        {error}
                                    </p>
                                )}
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                className="mt-4 gap-2 px-6"
                                onClick={() => {
                                    setStep("idle");
                                    setError("");
                                }}
                            >
                                {t("retry")}
                            </Button>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
