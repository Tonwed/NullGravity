"use client";

import { useTranslations } from "next-intl";
import { useState, useEffect, useCallback, useRef } from "react";
import {
    Plus,
    Search,
    MoreHorizontal,
    RefreshCw,
    Pencil,
    Trash2,
    Inbox,
    Shield,
    Loader2,
    Info,
    GripVertical,
    Rocket,
    Fingerprint,
    AlertTriangle,
    Download,
    Upload,
} from "lucide-react";
import { useWebSocket } from "@/components/providers/websocket-provider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AddAccountDialog } from "@/components/account/add-account-dialog";
import { AccountDetailsDialog } from "@/components/account/account-details-dialog";
import { DeviceFingerprintDialog } from "@/components/account/device-fingerprint-dialog";
import { ExportDialog } from "@/components/account/export-dialog";
import { ImportDialog } from "@/components/account/import-dialog";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent,
    DragStartEvent,
    DragOverlay,
} from "@dnd-kit/core";
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    verticalListSortingStrategy,
    useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const API_BASE = "http://127.0.0.1:8046/api";

interface AccountItem {
    id: string;
    email: string;
    display_name: string | null;
    avatar_url: string | null;
    avatar_cached: boolean;
    provider: string;
    status: string;
    label: string | null;
    quota_percent: number;
    is_forbidden: boolean;
    is_disabled: boolean;
    token_expires_at: string | null;
    created_at: string;
    updated_at: string;
    last_sync_at: string | null;

    tier: string | null;
    status_reason: string | null;
    status_details: { validation_url?: string; message?: string } | null;
    ineligible_tiers: any[] | null;
    quota_buckets: any[] | null;
    models: any[] | null;
    device_profile: any | null;

    credentials?: {
        client_type: string;
        updated_at: string;
        token_expires_at: string | null;
        tier: string | null;
        models: { name: string; remainingFraction?: number; resetTime?: string }[] | null;
        quota_data: any[] | null;
        last_sync_at: string | null;
    }[];
}

function getDisplayStatus(account: AccountItem): string {
    if (account.status_reason === "VALIDATION_REQUIRED") return "validation_required";
    if (account.is_forbidden) return "forbidden";
    if (account.is_disabled) return "disabled";
    return account.status;
}

function formatTimeAgo(dateStr: string | null): string {
    if (!dateStr) return "—";
    const utcStr = dateStr.endsWith("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
    const date = new Date(utcStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
}

function formatResetCountdown(resetTimeStr: string | null): { text: string; hours: number } | null {
    if (!resetTimeStr) return null;
    try {
        const resetDate = new Date(resetTimeStr);
        const now = new Date();
        const diffMs = resetDate.getTime() - now.getTime();
        if (diffMs <= 0) return null; // Already passed

        const diffMins = Math.floor(diffMs / 60000);
        const diffHrsToken = diffMins / 60; // floating point hours

        if (diffMins < 60) return { text: `${diffMins}m`, hours: diffHrsToken };

        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs >= 24) {
            const diffDays = Math.floor(diffHrs / 24);
            const hrsRem = diffHrs % 24;
            return { text: `${diffDays}d ${hrsRem}h`, hours: diffHrsToken };
        }

        const minsRem = diffMins % 60;
        return { text: `${diffHrs}h ${minsRem}m`, hours: diffHrsToken };
    } catch {
        return null;
    }
}

const statusDotColors: Record<string, string> = {
    active: "bg-emerald-500",
    inactive: "bg-amber-500",
    disabled: "bg-muted-foreground/40",
    forbidden: "bg-red-500",
    validation_required: "bg-yellow-500 animate-pulse",
};

function getModelQuota(cred: AccountItem["credentials"], clientType: string, modelKey: string): { pct: number | null, resetTime: string | null } {
    const c = cred?.find(c => c.client_type === clientType);
    if (!c?.models) return { pct: null, resetTime: null };
    const model = c.models.find(m => m.name?.toLowerCase().includes(modelKey.toLowerCase()));
    if (!model) return { pct: null, resetTime: null };
    // If remainingFraction is missing but model exists, quota is exhausted (0%)
    const fraction = model.remainingFraction;
    return {
        pct: fraction !== undefined && fraction !== null ? Math.round(fraction * 100) : 0,
        resetTime: model.resetTime || null
    };
}

const TIER_NAMES: Record<string, string> = {
    "free-tier": "Gemini Basic",
    "standard-tier": "Gemini Code Assist",
    "g1-pro-tier": "Google AI Pro",
    "g1-standard-tier": "Google AI Standard",
};

const PRO_TIERS = new Set(["g1-pro-tier"]);

const CACHE_KEY = "nullgravity_accounts_cache";

interface SortableAccountItemProps {
    account: AccountItem;
    t: any;
    refreshingIds: Set<string>;
    handleRefreshAccount: (id: string) => void;
    handleLaunch: (id: string) => void;
    setSelectedAccount: (account: AccountItem) => void;
    handleDelete: (id: string) => void;
    openFingerprintDialog: (account: AccountItem) => void;
    openAddAccountDialog: (options?: { targetEmail?: string }) => void;
    openValidationDialog: (account: AccountItem) => void;
    handleExportAccount: (id: string) => void;
}

interface AccountRowProps extends SortableAccountItemProps {
    style?: React.CSSProperties;
    isDragging?: boolean;
    isOverlay?: boolean;
    dragAttributes?: any;
    dragListeners?: any;
    domRef?: (node: HTMLElement | null) => void;
}

function AccountRow({
    account,
    t,
    refreshingIds,
    handleRefreshAccount,
    handleLaunch,
    setSelectedAccount,
    handleDelete,
    openFingerprintDialog,
    openAddAccountDialog,
    openValidationDialog,
    handleExportAccount,
    style,
    isDragging,
    isOverlay,
    dragAttributes,
    dragListeners,
    domRef,
}: AccountRowProps) {
    const displayStatus = getDisplayStatus(account);
    const isPaid = account.tier && account.tier !== "free-tier";
    const hasAntigravity = account.credentials?.some(c => c.client_type === "antigravity");

    // Antigravity quota only
    const quotaModels = [
        { label: "Gemini", key: "gemini", ...getModelQuota(account.credentials, "antigravity", "gemini-3.1-pro") },
        { label: "Gemini Image", key: "gemini-image", ...getModelQuota(account.credentials, "antigravity", "gemini-3.1-flash-image") },
        { label: "Claude", key: "claude", ...getModelQuota(account.credentials, "antigravity", "claude-opus") },
    ];

    return (
        <div
            ref={domRef}
            style={style}
            className={`group grid grid-cols-[250px_100px_105px_105px_105px_80px_auto] items-center gap-3 border-b border-border/60 px-4 py-2.5 text-[13px] last:border-b-0 transition-colors bg-card ${isOverlay ? "shadow-xl ring-1 ring-border rounded-md cursor-grabbing" : isDragging ? "opacity-30" : "hover:bg-accent/40"}`}
        >
            {/* Account info */}
            <div className="flex items-center gap-2.5 min-w-0">
                {/* Drag Handle */}
                <div
                    {...dragAttributes}
                    {...dragListeners}
                    className="cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-foreground mr-1 flex-shrink-0"
                    title="Drag to reorder"
                >
                    <GripVertical className="h-4 w-4" />
                </div>

                <div className={`relative h-9 w-9 rounded-full flex shrink-0 items-center justify-center ${isPaid ? "border-google-colored" : ""}`}>
                    <div className={`h-full w-full rounded-full ${isPaid ? "bg-background p-[2px]" : ""}`}>
                        {account.avatar_url ? (
                            <img
                                src={account.avatar_cached
                                    ? `${API_BASE}/accounts/${account.id}/avatar`
                                    : account.avatar_url
                                }
                                alt={account.display_name || account.email}
                                className="h-full w-full rounded-full object-cover bg-background"
                                referrerPolicy="no-referrer"
                            />
                        ) : (
                            <div className="flex h-full w-full items-center justify-center rounded-full bg-secondary text-xs font-medium text-muted-foreground">
                                {account.email[0]?.toUpperCase() ?? "?"}
                            </div>
                        )}
                    </div>
                </div>
                <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                        <span className={`inline-block h-2 w-2 rounded-full shrink-0 ${statusDotColors[displayStatus] ?? "bg-muted-foreground/40"}`} title={displayStatus} />
                        <span className="truncate font-medium">{account.display_name || account.email}</span>
                    </div>
                    {account.display_name && (
                        <div className="truncate text-[11px] text-muted-foreground">{account.email}</div>
                    )}
                </div>
            </div>

            {/* Subscription */}
            {PRO_TIERS.has(account.tier || "") ? (
                <Badge variant="secondary" className="w-fit text-[10px] font-medium px-1.5 py-0 bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    {TIER_NAMES[account.tier || ""]}
                </Badge>
            ) : (
                <Badge variant="secondary" className="w-fit text-[10px] bg-secondary/50 text-muted-foreground font-normal px-1.5 py-0">
                    {TIER_NAMES[account.tier || ""] || account.tier || "Free"}
                </Badge>
            )}

            {/* Quota Model 1 */}
            <div className="flex flex-col gap-1 w-full max-w-[90px]" title={`${quotaModels[0].label}: ${quotaModels[0].pct !== null ? quotaModels[0].pct + '%' : 'N/A'}`}>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                        className={`h-full rounded-full transition-all ${quotaModels[0].pct === null ? "bg-muted-foreground/20"
                            : quotaModels[0].pct > 60 ? "bg-emerald-500"
                                : quotaModels[0].pct > 30 ? "bg-amber-500"
                                    : "bg-red-500"
                            }`}
                        style={{ width: `${quotaModels[0].pct ?? 0}%` }}
                    />
                </div>
                <div className="flex items-center justify-between w-full text-[11px] leading-none">
                    {(() => {
                        const countdown = formatResetCountdown(quotaModels[0].resetTime);
                        return (
                            <span className={countdown && countdown.hours < 8 ? "text-emerald-500 font-medium" : "text-muted-foreground"}>
                                {countdown ? countdown.text : ""}
                            </span>
                        );
                    })()}
                    <span className="text-muted-foreground">
                        {quotaModels[0].pct !== null ? `${quotaModels[0].pct}%` : "—"}
                    </span>
                </div>
            </div>

            {/* Quota Model 2 */}
            <div className="flex flex-col gap-1 w-full max-w-[90px]" title={`${quotaModels[1].label}: ${quotaModels[1].pct !== null ? quotaModels[1].pct + '%' : 'N/A'}`}>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                        className={`h-full rounded-full transition-all ${quotaModels[1].pct === null ? "bg-muted-foreground/20"
                            : quotaModels[1].pct > 60 ? "bg-emerald-500"
                                : quotaModels[1].pct > 30 ? "bg-amber-500"
                                    : "bg-red-500"
                            }`}
                        style={{ width: `${quotaModels[1].pct ?? 0}%` }}
                    />
                </div>
                <div className="flex items-center justify-between w-full text-[11px] leading-none">
                    {(() => {
                        const countdown = formatResetCountdown(quotaModels[1].resetTime);
                        return (
                            <span className={countdown && countdown.hours < 8 ? "text-emerald-500 font-medium" : "text-muted-foreground"}>
                                {countdown ? countdown.text : ""}
                            </span>
                        );
                    })()}
                    <span className="text-muted-foreground">
                        {quotaModels[1].pct !== null ? `${quotaModels[1].pct}%` : "—"}
                    </span>
                </div>
            </div>

            {/* Quota Model 3 */}
            <div className="flex flex-col gap-1 w-full max-w-[90px]" title={`${quotaModels[2].label}: ${quotaModels[2].pct !== null ? quotaModels[2].pct + '%' : 'N/A'}`}>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                        className={`h-full rounded-full transition-all ${quotaModels[2].pct === null ? "bg-muted-foreground/20"
                            : quotaModels[2].pct > 60 ? "bg-emerald-500"
                                : quotaModels[2].pct > 30 ? "bg-amber-500"
                                    : "bg-red-500"
                            }`}
                        style={{ width: `${quotaModels[2].pct ?? 0}%` }}
                    />
                </div>
                <div className="flex items-center justify-between w-full text-[11px] leading-none">
                    {(() => {
                        const countdown = formatResetCountdown(quotaModels[2].resetTime);
                        return (
                            <span className={countdown && countdown.hours < 8 ? "text-emerald-500 font-medium" : "text-muted-foreground"}>
                                {countdown ? countdown.text : ""}
                            </span>
                        );
                    })()}
                    <span className="text-muted-foreground">
                        {quotaModels[2].pct !== null ? `${quotaModels[2].pct}%` : "—"}
                    </span>
                </div>
            </div>

            {/* Last Sync */}
            <span className="text-xs text-muted-foreground pl-3">
                {formatTimeAgo(account.last_sync_at)}
            </span>

            {/* Actions */}
            <div className="flex items-center gap-1 justify-end">
                {account.status_reason === "VALIDATION_REQUIRED" && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20"
                        title="Action Required"
                        onClick={(e) => {
                            e.stopPropagation();
                            openValidationDialog(account);
                        }}
                    >
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                    </Button>
                )}
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                    onClick={() => handleRefreshAccount(account.id)}
                    disabled={refreshingIds.has(account.id)}
                    title={t("refresh")}
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${refreshingIds.has(account.id) ? "animate-spin" : ""}`} />
                </Button>
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                    onClick={() => setSelectedAccount(account)}
                    title={t("info") || "Info"}
                >
                    <Info className="h-3.5 w-3.5" />
                </Button>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                        >
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                        {hasAntigravity && (
                            <DropdownMenuItem
                                className="gap-2 text-xs"
                                onClick={() => handleLaunch(account.id)}
                            >
                                <Rocket className="h-3 w-3" />
                                {t("openInAntigravity")}
                            </DropdownMenuItem>
                        )}
                        {!hasAntigravity && (
                            <DropdownMenuItem
                                className="gap-2 text-xs"
                                onClick={() => openAddAccountDialog({ targetEmail: account.email })}
                            >
                                <div className="flex items-center justify-center w-3 h-3">
                                    <img src="/antigravity-logo.png" className="w-full h-full object-contain" alt="" />
                                </div>
                                {t("connectAntigravity")}
                            </DropdownMenuItem>
                        )}
                        <DropdownMenuItem
                            className="gap-2 text-xs"
                            onClick={() => openFingerprintDialog(account)}
                        >
                            <Fingerprint className="h-3 w-3" />
                            {t("deviceFingerprint")}
                        </DropdownMenuItem>
                        <DropdownMenuItem className="gap-2 text-xs">
                            <Pencil className="h-3 w-3" />
                            {t("edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            className="gap-2 text-xs"
                            onClick={() => handleExportAccount(account.id)}
                        >
                            <Upload className="h-3 w-3" />
                            {t("exportTitle")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            className="gap-2 text-xs text-destructive"
                            onClick={() => handleDelete(account.id)}
                        >
                            <Trash2 className="h-3 w-3" />
                            {t("delete")}
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </div>
    );
}

function SortableAccountItem(props: SortableAccountItemProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id: props.account.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 50 : "auto",
        position: "relative" as const,
    };

    return (
        <AccountRow
            {...props}
            domRef={setNodeRef}
            style={style}
            isDragging={isDragging}
            dragAttributes={attributes}
            dragListeners={listeners}
        />
    );
}



export default function AccountsPage() {
    const t = useTranslations("accounts");
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const [addDialogTargetEmail, setAddDialogTargetEmail] = useState<string | undefined>();
    const [accounts, setAccounts] = useState<AccountItem[]>([]);
    const [loading, setLoading] = useState(true);

    const [search, setSearch] = useState("");
    const [sortOrder, setSortOrder] = useState<string>("created_at_desc");
    const [refreshingIds, setRefreshingIds] = useState<Set<string>>(new Set());
    const [selectedAccount, setSelectedAccount] = useState<AccountItem | null>(null);
    const [fingerprintAccount, setFingerprintAccount] = useState<AccountItem | null>(null);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [accountToDelete, setAccountToDelete] = useState<string | null>(null);
    const [validationAccount, setValidationAccount] = useState<AccountItem | null>(null);
    const [exportOpen, setExportOpen] = useState(false);
    const [exportAccountIds, setExportAccountIds] = useState<string[]>([]);
    const [importOpen, setImportOpen] = useState(false);

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const handleDragStart = (event: DragStartEvent) => {
        setActiveId(event.active.id as string);
    };

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        setActiveId(null);
        if (over && active.id !== over.id) {
            setAccounts((items) => {
                const oldIndex = items.findIndex((item) => item.id === active.id);
                const newIndex = items.findIndex((item) => item.id === over.id);
                const newItems = arrayMove(items, oldIndex, newIndex);
                try { localStorage.setItem(CACHE_KEY, JSON.stringify(newItems)); } catch { }
                return newItems;
            });
        }
    };

    // Hydrate from localStorage cache on mount (client-only)
    useEffect(() => {
        try {
            const cached = localStorage.getItem(CACHE_KEY);
            if (cached) {
                const parsed = JSON.parse(cached);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    setAccounts(parsed);
                }
            }
        } catch { }
    }, []);

    const fetchAccounts = useCallback(async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            const params = new URLSearchParams({ page: "1", page_size: "100" });
            params.append("sort_order", sortOrder);
            if (search) params.set("search", search);
            const res = await fetch(`${API_BASE}/accounts/?${params.toString()}`, {
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            });
            if (!res.ok) throw new Error("Failed to fetch");
            const data = await res.json();

            // Sort based on localStorage
            try {
                const cached = localStorage.getItem(CACHE_KEY);
                if (cached) {
                    const parsed = JSON.parse(cached);
                    if (Array.isArray(parsed)) {
                        const orderMap = new Map();
                        parsed.forEach((item: any, index: number) => orderMap.set(item.id, index));

                        // Only sort if we have order info
                        if (orderMap.size > 0) {
                            data.items.sort((a: any, b: any) => {
                                const indexA = orderMap.has(a.id) ? orderMap.get(a.id) : 999999;
                                const indexB = orderMap.has(b.id) ? orderMap.get(b.id) : 999999;
                                return indexA - indexB;
                            });
                        }
                    }
                }
            } catch { }

            setAccounts(data.items);
            try { localStorage.setItem(CACHE_KEY, JSON.stringify(data.items)); } catch { }
        } catch {
            // Network error — backend may not be running
        } finally {
            if (!silent) setLoading(false);
        }
    }, [search, sortOrder]);

    // WebSocket for real-time sync status
    // WebSocket for real-time sync status
    const { subscribe } = useWebSocket();
    useEffect(() => {
        const unsubscribe = subscribe((data: any) => {
            console.log("AccountsPage received:", data);
            if (data && data.type === "account_sync_start" && data.account_id) {
                setRefreshingIds(prev => {
                    const next = new Set(prev);
                    next.add(data.account_id);
                    return next;
                });
            } else if (data && data.type === "account_sync_end" && data.account_id) {
                setRefreshingIds(prev => {
                    const next = new Set(prev);
                    next.delete(data.account_id);
                    return next;
                });
                fetchAccounts(true);
            }
        });
        return unsubscribe;
    }, [fetchAccounts, subscribe]);

    useEffect(() => {
        fetchAccounts();

        // Poll every 10s for updates
        const interval = setInterval(() => {
            if (!activeId) fetchAccounts(true);
        }, 10000);

        // Refresh on focus
        const onFocus = () => {
            if (!activeId) fetchAccounts(true);
        };
        window.addEventListener("focus", onFocus);

        return () => {
            clearInterval(interval);
            window.removeEventListener("focus", onFocus);
        };
    }, [fetchAccounts, activeId]);

    const openDeleteConfirm = (id: string) => {
        const acc = accounts.find((a) => a.id === id);
        if (acc) setAccountToDelete(acc.id);
    };

    const confirmDelete = async () => {
        if (!accountToDelete) return;
        try {
            const res = await fetch(`${API_BASE}/accounts/${accountToDelete}`, { method: "DELETE" });
            if (res.ok) {
                fetchAccounts();
            }
        } catch {
            // ignore
        }
        setAccountToDelete(null);
    };

    const handleRefreshAccount = async (id: string) => {
        setRefreshingIds((prev) => new Set(prev).add(id));
        try {
            // 1. Refresh all credential tokens (gemini_cli + antigravity)
            await fetch(`${API_BASE}/auth/google/refresh/${id}`, { method: "POST" });
            // 2. Refresh userinfo (display_name, avatar)
            await fetch(`${API_BASE}/auth/google/userinfo/${id}`, { method: "POST" });
            // 3. Run sync (tier, quota, models) — handles both clients
            await fetch(`${API_BASE}/auth/google/setup/${id}`, { method: "POST" });
            // 4. Reload the account list to show updated info
            await fetchAccounts();
        } catch {
            // ignore network errors
        } finally {
            setRefreshingIds((prev) => {
                const next = new Set(prev);
                next.delete(id);
                return next;
            });
        }
    };

    const handleLaunch = async (id: string) => {
        try {
            await fetch(`${API_BASE}/accounts/${id}/launch`, { method: "POST" });
        } catch (e) {
            console.error("Failed to launch", e);
            // Optionally show alert or toast here
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
                <div className="flex items-center gap-1.5">
                    <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5 text-xs"
                        onClick={() => setImportOpen(true)}
                    >
                        <Download className="h-3.5 w-3.5" />
                        {t("importTitle")}
                    </Button>
                    <Button
                        size="sm"
                        className="gap-1.5 text-xs"
                        onClick={() => {
                            setAddDialogTargetEmail(undefined);
                            setAddDialogOpen(true);
                        }}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        {t("addAccount")}
                    </Button>
                </div>
            </div>

            {/* Search */}
            <div className="flex items-center gap-2">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        placeholder={t("search")}
                        className="h-8 pl-9 text-xs"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    className="h-8 w-8 p-0"
                    onClick={() => fetchAccounts()}
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                </Button>
            </div>

            {/* Table */}
            <div className="rounded-lg border border-border bg-card overflow-hidden">
                {/* Header */}
                <div className="grid grid-cols-[250px_100px_105px_105px_105px_80px_auto] gap-3 border-b border-border px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    <span>{t("email")}</span>
                    <span>{t("subscription") || "Subscription"}</span>
                    <span>Gemini</span>
                    <span>Gemini Image</span>
                    <span>Claude</span>
                    <span className="pl-3">{t("lastSync")}</span>
                    <span></span>
                </div>

                {/* Empty state */}
                {!loading && accounts.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                        <Inbox className="h-8 w-8 text-muted-foreground/40 mb-3" />
                        <p className="text-sm font-medium text-muted-foreground">{t("noAccounts")}</p>
                        <p className="text-xs text-muted-foreground/70 mt-1">{t("noAccountsDesc")}</p>
                        <Button
                            size="sm"
                            variant="outline"
                            className="mt-4 gap-1.5 text-xs"
                            onClick={() => {
                                setAddDialogTargetEmail(undefined);
                                setAddDialogOpen(true);
                            }}
                        >
                            <Plus className="h-3.5 w-3.5" />
                            {t("addAccount")}
                        </Button>
                    </div>
                )}

                {/* Loading skeleton */}
                {loading && accounts.length === 0 && (
                    <div className="space-y-0">
                        {[1, 2, 3].map((i) => (
                            <div
                                key={i}
                                className="grid grid-cols-[250px_100px_105px_105px_105px_80px_auto] items-center gap-3 border-b border-border/60 px-4 py-3"
                            >
                                <div className="flex items-center gap-2.5">
                                    <div className="h-7 w-7 rounded-full bg-muted animate-pulse" />
                                    <div className="h-3.5 w-32 rounded bg-muted animate-pulse" />
                                </div>
                                <div className="h-4 w-16 rounded bg-muted animate-pulse" />
                                <div className="h-1.5 w-14 rounded bg-muted animate-pulse" />
                                <div className="h-1.5 w-14 rounded bg-muted animate-pulse" />
                                <div className="h-1.5 w-14 rounded bg-muted animate-pulse" />
                                <div className="h-3 w-14 rounded bg-muted animate-pulse ml-3" />
                                <div />
                            </div>
                        ))}
                    </div>
                )}

                {/* Rows */}
                <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragStart={handleDragStart}
                    onDragEnd={handleDragEnd}
                >
                    <SortableContext
                        items={accounts.map((a) => a.id)}
                        strategy={verticalListSortingStrategy}
                    >
                        {accounts.map((account) => (
                            <SortableAccountItem
                                key={account.id}
                                account={account}
                                t={t}
                                refreshingIds={refreshingIds}
                                handleRefreshAccount={handleRefreshAccount}
                                handleLaunch={handleLaunch}
                                setSelectedAccount={setSelectedAccount}
                                handleDelete={openDeleteConfirm}
                                openFingerprintDialog={setFingerprintAccount}
                                openAddAccountDialog={(opts) => {
                                    setAddDialogTargetEmail(opts?.targetEmail);
                                    setAddDialogOpen(true);
                                }}
                                openValidationDialog={setValidationAccount}
                                handleExportAccount={(id) => {
                                    setExportAccountIds([id]);
                                    setExportOpen(true);
                                }}
                            />
                        ))}
                    </SortableContext>
                    <DragOverlay>
                        {activeId ? (
                            <AccountRow
                                account={accounts.find((a) => a.id === activeId)!}
                                t={t}
                                refreshingIds={refreshingIds}
                                handleRefreshAccount={handleRefreshAccount}
                                handleLaunch={handleLaunch}
                                setSelectedAccount={setSelectedAccount}
                                handleDelete={openDeleteConfirm}
                                openFingerprintDialog={setFingerprintAccount}
                                openAddAccountDialog={() => { }}
                                isOverlay
                                openValidationDialog={() => { }}
                                handleExportAccount={() => { }}
                            />
                        ) : null}
                    </DragOverlay>
                </DndContext>
            </div>

            {/* Validation Dialog */}
            <Dialog open={!!validationAccount} onOpenChange={(open) => !open && setValidationAccount(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-yellow-500">
                            <AlertTriangle className="h-5 w-5" />
                            {t("validation.title") || "Account Action Required"}
                        </DialogTitle>
                        <DialogDescription className="pt-2 text-foreground">
                            {validationAccount?.status_details?.message || t("validation.message") || "Your account requires verification to correct an issue with Google services."}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="text-sm text-muted-foreground">
                        {t("validation.note") || "Please verify your account to restore functionality."}
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setValidationAccount(null)}>
                            {t("validation.close") || "Close"}
                        </Button>
                        {validationAccount?.status_details?.validation_url ? (
                            <Button onClick={() => window.open(validationAccount.status_details!.validation_url, "_blank")}>
                                {t("validation.button") || "Verify Account"}
                            </Button>
                        ) : (
                            <Button asChild>
                                <a href="https://accounts.google.com/" target="_blank" rel="noreferrer">
                                    {t("validation.fallback") || "Go to Google Account"}
                                </a>
                            </Button>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Add Account Dialog */}
            <AddAccountDialog
                open={addDialogOpen}
                onOpenChange={(open) => {
                    setAddDialogOpen(open);
                    if (!open) setTimeout(() => setAddDialogTargetEmail(undefined), 200);
                }}
                onAccountAdded={fetchAccounts}
                targetEmail={addDialogTargetEmail}
            />

            <AccountDetailsDialog
                open={!!selectedAccount}
                onOpenChange={(open) => !open && setSelectedAccount(null)}
                account={selectedAccount}
            />

            <DeviceFingerprintDialog
                open={!!fingerprintAccount}
                onOpenChange={(open) => !open && setFingerprintAccount(null)}
                accountId={fingerprintAccount?.id || null}
                accountEmail={fingerprintAccount?.email || null}
            />

            <Dialog open={!!accountToDelete} onOpenChange={(open) => !open && setAccountToDelete(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{t("deleteConfirmTitle")}</DialogTitle>
                        <DialogDescription>
                            {t("deleteConfirmDesc")}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setAccountToDelete(null)}
                        >
                            {t("cancel") || "Cancel"}
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={confirmDelete}
                        >
                            {t("delete") || "Delete"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <ExportDialog
                open={exportOpen}
                onOpenChange={(open) => {
                    setExportOpen(open);
                    if (!open) setExportAccountIds([]);
                }}
                accountIds={exportAccountIds}
            />

            <ImportDialog
                open={importOpen}
                onOpenChange={setImportOpen}
                clientType={"antigravity"}
                onComplete={fetchAccounts}
            />
        </div>
    );
}
