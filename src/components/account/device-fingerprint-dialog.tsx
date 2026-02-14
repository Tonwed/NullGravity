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
import { Badge } from "@/components/ui/badge";
import {
    Fingerprint,
    RefreshCw,
    Copy,
    Check,
    AlertTriangle,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8046/api";

interface DeviceProfile {
    machineId: string;
    macMachineId: string;
    devDeviceId: string;
    sqmId: string;
}

interface DeviceFingerprintDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    accountId: string | null;
    accountEmail: string | null;
}

const FIELD_LABELS: Record<string, { label: string; description: string }> = {
    machineId: {
        label: "Machine ID",
        description: "Primary machine identifier",
    },
    macMachineId: {
        label: "MAC Machine ID",
        description: "Hardware-based machine identifier",
    },
    devDeviceId: {
        label: "Dev Device ID",
        description: "Developer device identifier (UUID)",
    },
    sqmId: {
        label: "SQM ID",
        description: "Software quality metrics identifier",
    },
};

export function DeviceFingerprintDialog({
    open,
    onOpenChange,
    accountId,
    accountEmail,
}: DeviceFingerprintDialogProps) {
    const t = useTranslations("accounts");
    const [profile, setProfile] = useState<DeviceProfile | null>(null);
    const [loading, setLoading] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const [copiedField, setCopiedField] = useState<string | null>(null);
    const [showConfirm, setShowConfirm] = useState(false);

    const fetchProfile = useCallback(async () => {
        if (!accountId) return;
        setLoading(true);
        try {
            const res = await fetch(
                `${API_BASE}/accounts/${accountId}/device-profile`
            );
            if (res.ok) {
                const data = await res.json();
                setProfile(data.device_profile);
            }
        } catch {
            // ignore
        } finally {
            setLoading(false);
        }
    }, [accountId]);

    useEffect(() => {
        if (open && accountId) {
            fetchProfile();
            setShowConfirm(false);
            setCopiedField(null);
        }
    }, [open, accountId, fetchProfile]);

    const handleRegenerate = async () => {
        if (!accountId) return;
        setRegenerating(true);
        try {
            const res = await fetch(
                `${API_BASE}/accounts/${accountId}/device-profile/regenerate`,
                { method: "POST" }
            );
            if (res.ok) {
                const data = await res.json();
                setProfile(data.device_profile);
                setShowConfirm(false);
            }
        } catch {
            // ignore
        } finally {
            setRegenerating(false);
        }
    };

    const handleCopy = async (field: string, value: string) => {
        try {
            await navigator.clipboard.writeText(value);
            setCopiedField(field);
            setTimeout(() => setCopiedField(null), 2000);
        } catch {
            // ignore
        }
    };

    const handleCopyAll = async () => {
        if (!profile) return;
        const text = Object.entries(profile)
            .map(([key, value]) => `${key}: ${value}`)
            .join("\n");
        try {
            await navigator.clipboard.writeText(text);
            setCopiedField("__all__");
            setTimeout(() => setCopiedField(null), 2000);
        } catch {
            // ignore
        }
    };

    if (!accountId) return null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[520px] gap-0 p-0 overflow-hidden">
                <DialogHeader className="px-6 pt-6 pb-4 bg-muted/30 border-b border-border/50 pr-10">
                    <div className="flex items-center gap-3">
                        <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
                            <Fingerprint className="h-4.5 w-4.5 text-primary" />
                        </div>
                        <div>
                            <DialogTitle className="text-base font-semibold">
                                {t("deviceFingerprintTitle")}
                            </DialogTitle>
                            <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                                {accountEmail}
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                <div className="px-6 py-4 space-y-4">
                    {/* Description */}
                    <p className="text-xs text-muted-foreground leading-relaxed">
                        {t("deviceFingerprintDesc")}
                    </p>

                    {/* Fingerprint fields */}
                    {loading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4].map((i) => (
                                <div
                                    key={i}
                                    className="rounded-lg border border-border/60 p-3"
                                >
                                    <div className="h-3 w-24 rounded bg-muted animate-pulse mb-2" />
                                    <div className="h-4 w-full rounded bg-muted animate-pulse" />
                                </div>
                            ))}
                        </div>
                    ) : profile ? (
                        <div className="space-y-2">
                            {Object.entries(FIELD_LABELS).map(
                                ([key, { label, description }]) => {
                                    const value =
                                        profile[
                                        key as keyof DeviceProfile
                                        ] || "—";
                                    const isCopied = copiedField === key;

                                    return (
                                        <div
                                            key={key}
                                            className="group rounded-lg border border-border/60 p-3 hover:border-border transition-colors"
                                        >
                                            <div className="flex items-center justify-between mb-1.5">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[11px] font-medium text-foreground">
                                                        {label}
                                                    </span>
                                                    <Badge
                                                        variant="outline"
                                                        className="text-[9px] px-1 py-0 text-muted-foreground/70 font-normal"
                                                    >
                                                        {description}
                                                    </Badge>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                                    onClick={() =>
                                                        handleCopy(key, value)
                                                    }
                                                >
                                                    {isCopied ? (
                                                        <Check className="h-3 w-3 text-green-500" />
                                                    ) : (
                                                        <Copy className="h-3 w-3 text-muted-foreground" />
                                                    )}
                                                </Button>
                                            </div>
                                            <code className="text-[11px] text-muted-foreground font-mono break-all select-all leading-relaxed">
                                                {value}
                                            </code>
                                        </div>
                                    );
                                }
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-8 text-sm text-muted-foreground">
                            Failed to load fingerprint data
                        </div>
                    )}

                    {/* Actions */}
                    {profile && (
                        <div className="flex items-center justify-between pt-2 border-t border-border/50">
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs gap-1.5"
                                onClick={handleCopyAll}
                            >
                                {copiedField === "__all__" ? (
                                    <>
                                        <Check className="h-3 w-3 text-green-500" />
                                        {t("fingerprintCopied")}
                                    </>
                                ) : (
                                    <>
                                        <Copy className="h-3 w-3" />
                                        {t("copyFingerprint")}
                                    </>
                                )}
                            </Button>

                            {showConfirm ? (
                                <div className="flex items-center gap-2">
                                    <div className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
                                        <AlertTriangle className="h-3 w-3" />
                                        <span className="max-w-[180px] truncate">
                                            {t("regenerateConfirm")}
                                        </span>
                                    </div>
                                    <Button
                                        variant="destructive"
                                        size="sm"
                                        className="h-7 text-xs"
                                        onClick={handleRegenerate}
                                        disabled={regenerating}
                                    >
                                        {regenerating ? (
                                            <RefreshCw className="h-3 w-3 animate-spin" />
                                        ) : (
                                            t("common:confirm") || "Confirm"
                                        )}
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-xs"
                                        onClick={() => setShowConfirm(false)}
                                    >
                                        {t("common:cancel") || "Cancel"}
                                    </Button>
                                </div>
                            ) : (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 text-xs gap-1.5 text-amber-600 dark:text-amber-400 border-amber-500/30 hover:bg-amber-500/5"
                                    onClick={() => setShowConfirm(true)}
                                >
                                    <RefreshCw className="h-3 w-3" />
                                    {t("regenerateFingerprint")}
                                </Button>
                            )}
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
