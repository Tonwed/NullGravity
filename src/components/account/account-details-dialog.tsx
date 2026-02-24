"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
    AlertTriangle,
    CheckCircle2,
    XCircle,
    Shield,
    Database,
    Clock,
    ChevronRight,
    ChevronDown
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AccountDetailsDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    account: any;
}

const TIER_NAMES: Record<string, string> = {
    "free-tier": "Gemini Basic",
    "standard-tier": "Gemini Code Assist",
    "g1-pro-tier": "Google AI Pro",
    "g1-standard-tier": "Google AI Standard",
};

const PRO_TIERS = new Set(["g1-pro-tier"]);

export function AccountDetailsDialog({
    open,
    onOpenChange,
    account
}: AccountDetailsDialogProps) {
    const t = useTranslations("accounts");
    const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

    if (!account) return null;

    const toggleSection = (section: string) => {
        setExpandedSections(prev => ({
            ...prev,
            [section]: !prev[section]
        }));
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px] gap-0 p-0 overflow-hidden focus:outline-none">
                <DialogHeader className="px-6 pt-6 pb-4 bg-muted/30 border-b border-border/50 pr-10">
                    <div className="flex items-center gap-4">
                        {(() => {
                            const isPaid = account.tier && account.tier !== "free-tier";
                            return (
                                <div className={`relative h-12 w-12 rounded-full ${isPaid ? "border-google-colored" : "border border-border"}`}>
                                    <div className={`h-full w-full rounded-full ${isPaid ? "bg-background p-[2px]" : ""}`}>
                                        {account.avatar_url ? (
                                            <img
                                                src={account.avatar_cached
                                                    ? `http://127.0.0.1:8046/api/accounts/${account.id}/avatar`
                                                    : account.avatar_url
                                                }
                                                alt={account.display_name || account.email}
                                                className="h-full w-full rounded-full object-cover bg-background"
                                                referrerPolicy="no-referrer"
                                            />
                                        ) : (
                                            <div className="flex h-full w-full items-center justify-center rounded-full bg-secondary text-lg font-medium text-muted-foreground bg-background">
                                                {account.email?.[0]?.toUpperCase() ?? "?"}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })()}
                        <div className="flex-1 min-w-0">
                            <DialogTitle className="text-lg font-semibold truncate">
                                {account.display_name || account.email}
                            </DialogTitle>
                            <DialogDescription className="truncate text-xs">
                                {account.email} • {account.provider}
                            </DialogDescription>
                        </div>
                        <div className="flex flex-col items-end gap-1.5">
                            <Badge
                                variant={account.is_forbidden ? "destructive" : "outline"}
                                className="uppercase text-[10px] tracking-wider"
                            >
                                {account.is_forbidden ? "Forbidden" : account.status}
                            </Badge>
                            {account.tier && (
                                PRO_TIERS.has(account.tier) ? (
                                    <Badge variant="outline" className="text-[10px] font-medium px-1.5 py-0 border-amber-500/40 bg-amber-500/5 text-amber-600 dark:text-amber-400">
                                        {TIER_NAMES[account.tier] || account.tier}
                                    </Badge>
                                ) : (
                                    <Badge variant="secondary" className="text-[10px]">
                                        {TIER_NAMES[account.tier] || account.tier}
                                    </Badge>
                                )
                            )}
                        </div>
                    </div>
                </DialogHeader>

                <ScrollArea className="h-[400px]">
                    <div className="p-6 space-y-6">
                        {/* Status / Issues */}
                        {account.status_reason && (
                            <div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 flex gap-3">
                                <AlertTriangle className="h-5 w-5 text-destructive shrink-0" />
                                <div className="space-y-1">
                                    <h4 className="text-sm font-medium text-destructive">Account Restricted</h4>
                                    <p className="text-xs text-destructive/80">
                                        Reason: {account.status_reason}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Ineligible Tiers */}
                        {account.ineligible_tiers && account.ineligible_tiers.length > 0 && (
                            <div className="space-y-3">
                                <h4 className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                                    <Shield className="h-4 w-4" />
                                    Tier Eligibility
                                </h4>
                                <div className="grid gap-2">
                                    {account.ineligible_tiers.map((tier: any, i: number) => (
                                        <div key={i} className="text-xs bg-muted/40 p-2.5 rounded border border-border/50 flex items-start gap-2.5">
                                            <XCircle className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                                            <div>
                                                <p className="font-medium text-foreground">{tier.tierName || "Unknown Tier"}</p>
                                                <p className="text-muted-foreground mt-0.5">{tier.reasonMessage || tier.reasonCode}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Quota Buckets */}
                        <div className="space-y-4">
                            <h4 className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                                <Database className="h-4 w-4" />
                                Quota Usage
                            </h4>

                            {(() => {
                                // Extract Antigravity credential
                                const antigravityCred = account.credentials?.find((c: any) => c.client_type === 'antigravity');
                                const antigravityModels = antigravityCred?.models || [];
                                const hasAntigravity = antigravityModels.length > 0;

                                if (!hasAntigravity) {
                                    return (
                                        <div className="text-xs text-muted-foreground py-4 italic border border-border/50 rounded-md bg-muted/20 text-center">
                                            No quota information available yet.<br />Try refreshing the account to sync data.
                                        </div>
                                    );
                                }

                                const renderQuotaSection = (id: string, models: any[], title: string, badgeVariant: "default" | "secondary" | "outline" = "outline") => {
                                    if (!models || models.length === 0) return null;

                                    const isExpanded = expandedSections[id];

                                    return (
                                        <div className="border border-border/60 rounded-lg overflow-hidden transition-all duration-200">
                                            <button
                                                onClick={() => toggleSection(id)}
                                                className="w-full flex items-center justify-between p-3 bg-muted/30 hover:bg-muted/50 transition-colors text-left group"
                                            >
                                                <div className="flex items-center gap-2">
                                                    {isExpanded ? (
                                                        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200" />
                                                    ) : (
                                                        <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform duration-200" />
                                                    )}
                                                    <span className="text-xs font-semibold text-foreground/90">{title}</span>
                                                </div>
                                                <Badge variant={badgeVariant} className="text-[10px] h-5 px-2 font-normal opacity-80 rounded-full transition-opacity group-hover:opacity-100">
                                                    {models.length} Models
                                                </Badge>
                                            </button>

                                            {isExpanded && (
                                                <div className="border-t border-border/40 bg-card/50 divide-y divide-border/40 animate-in slide-in-from-top-1 duration-200 fade-in">
                                                    {models
                                                        .slice()
                                                        .sort((a: any, b: any) => {
                                                            const fracA = a.remainingFraction ?? 1;
                                                            const fracB = b.remainingFraction ?? 1;
                                                            if (fracA !== fracB) return fracA - fracB;
                                                            return (a.name || a.modelId || "").localeCompare(b.name || b.modelId || "");
                                                        })
                                                        .map((bucket: any, i: number) => {
                                                            // Normalize model ID
                                                            const modelId = bucket.name || bucket.modelId || bucket.tokenType || "Unknown";

                                                            // Name cleaning
                                                            const cleanName = modelId
                                                                .replace(/_/g, " ")
                                                                .replace(/-/g, " ")
                                                                .replace(/\b\w/g, (l: string) => l.toUpperCase())
                                                                .replace("Gemini ", "Gemini ");

                                                            const fraction = bucket.remainingFraction;

                                                            // Handle time format
                                                            let resetTimeStr = null;
                                                            if (bucket.resetTime) {
                                                                try {
                                                                    resetTimeStr = new Date(bucket.resetTime).toLocaleString();
                                                                } catch (e) { resetTimeStr = bucket.resetTime; }
                                                            }

                                                            let remainingPercent = 0;
                                                            let displayValue = "Unknown";
                                                            let barColor = "bg-secondary";
                                                            let barWidth = 0;

                                                            if (fraction !== undefined) {
                                                                remainingPercent = Math.max(0, Math.min(100, fraction * 100));
                                                                displayValue = `${remainingPercent.toFixed(1)}%`;
                                                                barWidth = remainingPercent;

                                                                if (remainingPercent > 50) barColor = "bg-emerald-500";
                                                                else if (remainingPercent > 20) barColor = "bg-amber-500";
                                                                else barColor = "bg-destructive";
                                                            } else if (bucket.remainingAmount !== undefined) {
                                                                displayValue = `${bucket.remainingAmount}`;
                                                                barWidth = 100;
                                                            }

                                                            return (
                                                                <div key={i} className="p-3 text-xs space-y-2 hover:bg-muted/40 transition-colors group/item">
                                                                    <div className="flex justify-between items-center">
                                                                        <span className="font-medium truncate pr-2 text-foreground/90" title={modelId}>{cleanName}</span>
                                                                        <span className={`whitespace-nowrap tabular-nums font-mono ${fraction < 0.2 ? "text-destructive font-bold" : "text-muted-foreground"}`}>{displayValue}</span>
                                                                    </div>

                                                                    {fraction !== undefined && (
                                                                        <div className="h-1.5 w-full bg-secondary/40 rounded-full overflow-hidden">
                                                                            <div
                                                                                className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                                                                                style={{ width: `${Math.max(barWidth, 2)}%` }}
                                                                            />
                                                                        </div>
                                                                    )}

                                                                    <div className="flex items-center justify-between text-[10px] text-muted-foreground/60 group-hover/item:text-muted-foreground/85 transition-colors">
                                                                        <span className="font-mono opacity-70 truncate max-w-[180px]">{modelId}</span>
                                                                        {resetTimeStr && (
                                                                            <div className="flex items-center gap-1 shrink-0">
                                                                                <Clock className="h-3 w-3 opacity-70" />
                                                                                <span>Reset: {resetTimeStr}</span>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                </div>
                                            )}
                                        </div>
                                    );
                                };

                                return (
                                    <div className="space-y-3">
                                        {renderQuotaSection("antigravity", antigravityModels, "Antigravity Quota", "default")}
                                    </div>
                                );
                            })()}
                        </div>
                    </div>
                </ScrollArea>
            </DialogContent>
        </Dialog>
    );
}
