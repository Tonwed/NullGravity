"use client";

import { useTranslations } from "next-intl";
import { useState, useEffect, useCallback } from "react";
import {
    Network,
    Play,
    Square,
    RefreshCw,
    Copy,
    Check,
    Loader2,
    Users,
    Zap,
    Info,
    Key,
    Trash2,
    Plus,
    Power,
    KeyRound,
    Clock,
    FileText,
    ChevronRight,
    ChevronDown,
    Inbox,
    RefreshCcw,
    Box,
    ArrowRight,
    Pencil,
    GripVertical,
    BarChart3,
} from "lucide-react";
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    type DragEndEvent,
} from "@dnd-kit/core";
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const API_BASE = "http://127.0.0.1:8046/api";

const sections = [
    { id: "proxy", icon: Network, labelKey: "antigravityProxy" as const, descKey: "antigravityProxyDesc" as const },
    { id: "models", icon: Box, labelKey: "modelsAndMapping" as const, descKey: "modelsAndMappingDesc" as const },
    { id: "tokens", icon: Key, labelKey: "tokenManagement" as const, descKey: "tokenManagementDesc" as const },
    { id: "logs", icon: FileText, labelKey: "proxyLogs" as const, descKey: "proxyLogsDesc" as const },
];

interface PoolAccount {
    id: string;
    email: string;
    status: "available" | "rate_limited" | "exhausted";
    remaining_seconds: number | null;
}

interface ProxyStatus {
    running: boolean;
    port: number;
    upstream: string;
    total_requests: number;
    total_rotations: number;
    started_at: string | null;
    current_account_email: string | null;
    current_account_id: string | null;
    pool_size: number;
    pool_available: number;
    pool_accounts: PoolAccount[];
    schedule_mode: string;
    pool_cooldown: number;
}

interface ApiToken {
    id: number;
    name: string;
    token: string;
    is_active: boolean;
    total_requests: number;
    last_used_at: string | null;
    created_at: string;
}

interface ProxyLog {
    id: number;
    method: string;
    path: string;
    api_format: string;        // "openai" or "anthropic"
    model: string;
    original_model: string;    // original model before mapping
    stream: boolean;
    status_code: number;
    duration_ms: number;
    timestamp: number;
    timestamp_iso: string;
    account_email: string;
    account_id: string;
    input_tokens: number;
    output_tokens: number;
    error: string;
    client_ip: string;
}

interface ModelMappingRule {
    id: string;
    pattern: string;
    target: string;
    is_active: boolean;
    priority: number;
    created_at: string;
}

function formatUptime(startedAt: string | null): string {
    if (!startedAt) return "—";
    const start = new Date(startedAt);
    const now = new Date();
    const diffMs = now.getTime() - start.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "< 1m";
    if (diffMin < 60) return `${diffMin}m`;
    const diffHr = Math.floor(diffMin / 60);
    const remMin = diffMin % 60;
    if (diffHr < 24) return `${diffHr}h ${remMin}m`;
    const diffDay = Math.floor(diffHr / 24);
    const remHr = diffHr % 24;
    return `${diffDay}d ${remHr}h`;
}

const AVAILABLE_MODELS = [
    { id: "claude-opus-4-6-thinking", name: "Claude Opus 4.6 Thinking", descKey: "modelDescClaudeOpus46Thinking", owner: "anthropic" },
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", descKey: "modelDescClaudeSonnet46", owner: "anthropic" },
    { id: "gemini-3.1-pro-high", name: "Gemini 3.1 Pro High", descKey: "modelDescGemini31ProHigh", owner: "google" },
    { id: "gemini-3.1-pro-low", name: "Gemini 3.1 Pro Low", descKey: "modelDescGemini31ProLow", owner: "google" },
    { id: "gemini-3-pro-high", name: "Gemini 3 Pro High", descKey: "modelDescGemini3ProHigh", owner: "google" },
    { id: "gemini-3-pro-low", name: "Gemini 3 Pro Low", descKey: "modelDescGemini3ProLow", owner: "google" },
    { id: "gemini-3.1-flash-image", name: "Gemini 3.1 Flash Image", descKey: "modelDescGemini3ProImage", owner: "google" },
    { id: "gemini-3-flash", name: "Gemini 3 Flash", descKey: "modelDescGemini3Flash", owner: "google" },
    { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", descKey: "modelDescGemini25Pro", owner: "google" },
    { id: "gemini-2.5-flash-thinking", name: "Gemini 2.5 Flash Thinking", descKey: "modelDescGemini25FlashThinking", owner: "google" },
    { id: "gemini-2.5-flash-lite", name: "Gemini 2.5 Flash Lite", descKey: "modelDescGemini25FlashLite", owner: "google" },
    { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", descKey: "modelDescGemini25Flash", owner: "google" },
];

function SortableMappingRow({ mapping, editingId, editPattern, setEditPattern, editTarget, setEditTarget, handleSaveMapping, handleCancelEdit, savingMapping, handleEditMappingInline, handleToggleMapping, setDeleteMappingConfirm, t, MODELS }: any) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id: mapping.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 10 : undefined,
    };

    if (editingId === mapping.id) {
        return (
            <div ref={setNodeRef} style={style} className="grid grid-cols-[24px_1fr_32px_1fr_60px_80px] gap-2 px-4 py-2 items-center bg-primary/5 border-l-2 border-l-primary">
                <div />
                <div>
                    <Input
                        value={editPattern}
                        onChange={(e: any) => setEditPattern(e.target.value)}
                        className="h-7 text-[11px] font-mono"
                        autoFocus
                        onKeyDown={(e: any) => { if (e.key === "Enter") handleSaveMapping(); if (e.key === "Escape") handleCancelEdit(); }}
                    />
                </div>
                <div className="flex justify-center">
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                </div>
                <div>
                    <Select value={editTarget} onValueChange={setEditTarget}>
                        <SelectTrigger className="h-7 text-[11px] font-mono">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {MODELS.map((m: any) => (
                                <SelectItem key={m.id} value={m.id} className="text-xs font-mono">
                                    {m.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div></div>
                <div className="flex items-center justify-end gap-1">
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-emerald-600" onClick={handleSaveMapping} disabled={!editPattern.trim() || !editTarget.trim() || savingMapping}>
                        {savingMapping ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCancelEdit}>
                        <Square className="h-2.5 w-2.5" />
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div ref={setNodeRef} style={style} className="group grid grid-cols-[24px_1fr_32px_1fr_60px_80px] gap-2 px-4 py-2.5 items-center hover:bg-muted/30 transition-colors">
            <div
                className="flex items-center justify-center cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground transition-colors"
                {...attributes}
                {...listeners}
            >
                <GripVertical className="h-3.5 w-3.5" />
            </div>
            <div className="font-mono text-[11px]">
                <span className="bg-muted px-1.5 py-0.5 rounded border border-border/50">
                    {mapping.pattern}
                </span>
            </div>
            <div className="flex justify-center">
                <ArrowRight className="h-3 w-3 text-muted-foreground" />
            </div>
            <div className="font-mono text-[11px]">
                <span className="bg-muted px-1.5 py-0.5 rounded border border-border/50">
                    {mapping.target}
                </span>
            </div>
            <div>
                <Switch
                    checked={mapping.is_active}
                    onCheckedChange={() => handleToggleMapping(mapping.id)}
                />
            </div>
            <div className="flex items-center justify-end gap-1">
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleEditMappingInline(mapping)}>
                    <Pencil className="h-3 w-3" />
                </Button>
                <Button variant="ghost" size="icon" className="h-6 w-6 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30" onClick={() => setDeleteMappingConfirm({ isOpen: true, id: mapping.id })}>
                    <Trash2 className="h-3 w-3" />
                </Button>
            </div>
        </div>
    );
}

export default function ApiProxyPage() {
    const t = useTranslations("apiProxy");
    const c = useTranslations("common");

    const [activeSection, setActiveSection] = useState("proxy");

    // Proxy State
    const [status, setStatus] = useState<ProxyStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [acting, setActing] = useState(false);
    const [port, setPort] = useState("9090");
    const [upstream, setUpstream] = useState("https://daily-cloudcode-pa.googleapis.com");
    const [copied, setCopied] = useState(false);
    const [copiedModelId, setCopiedModelId] = useState<string | null>(null);
    const [refreshingPool, setRefreshingPool] = useState(false);
    const [showShine, setShowShine] = useState(false);

    // Pool Settings State
    const [scheduleMode, setScheduleMode] = useState("balance");
    const [poolCooldown, setPoolCooldown] = useState("0");
    const [poolExpanded, setPoolExpanded] = useState(false);

    useEffect(() => {
        if (status?.running) {
            setShowShine(true);
            const timer = setTimeout(() => setShowShine(false), 2000);
            return () => clearTimeout(timer);
        }
    }, [status?.running]);

    // Token State
    const [tokens, setTokens] = useState<ApiToken[]>([]);
    const [loadingTokens, setLoadingTokens] = useState(false);
    const [newTokenName, setNewTokenName] = useState("");
    const [creatingToken, setCreatingToken] = useState(false);

    // Dialog State
    const [isTokenDialogOpen, setIsTokenDialogOpen] = useState(false);
    const [newlyGeneratedToken, setNewlyGeneratedToken] = useState<string | null>(null);
    const [dialogType, setDialogType] = useState<"create" | "regenerate">("create");
    const [confirmDialog, setConfirmDialog] = useState<{ isOpen: boolean, type: "regenerate" | "delete", tokenId: number | null }>({ isOpen: false, type: "regenerate", tokenId: null });
    const [isConfirming, setIsConfirming] = useState(false);

    // Logs State
    const [logs, setLogs] = useState<ProxyLog[]>([]);
    const [loadingLogs, setLoadingLogs] = useState(false);
    const [expandedLogId, setExpandedLogId] = useState<number | null>(null);

    // Model Mapping State
    const [mappings, setMappings] = useState<ModelMappingRule[]>([]);
    const [loadingMappings, setLoadingMappings] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null); // mapping id or "__new__"
    const [editPattern, setEditPattern] = useState("");
    const [editTarget, setEditTarget] = useState("");
    const [savingMapping, setSavingMapping] = useState(false);
    const [deleteMappingConfirm, setDeleteMappingConfirm] = useState<{ isOpen: boolean; id: string | null }>({ isOpen: false, id: null });

    // Token usage detail state
    const [usageTokenId, setUsageTokenId] = useState<number | null>(null);
    const [usageLogs, setUsageLogs] = useState<ProxyLog[]>([]);
    const [loadingUsage, setLoadingUsage] = useState(false);

    // DnD sensors
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    // Fetch Proxy Status
    const fetchStatus = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api-proxy/status`);
            if (res.ok) {
                const data = await res.json();
                setStatus(data);
                if (data.running) {
                    setPort(String(data.port));
                    setUpstream(data.upstream);
                }
                if (data.schedule_mode) setScheduleMode(data.schedule_mode);
                if (data.pool_cooldown !== undefined) setPoolCooldown(String(data.pool_cooldown));
            }
        } catch {
            // backend may not be running
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    // Fetch Tokens
    const fetchTokens = useCallback(async () => {
        setLoadingTokens(true);
        try {
            const res = await fetch(`${API_BASE}/api-tokens/`);
            if (res.ok) {
                const data = await res.json();
                setTokens(data.items || []);
            }
        } catch { }
        finally { setLoadingTokens(false); }
    }, []);

    useEffect(() => {
        if (activeSection === "tokens") {
            fetchTokens();
        }
    }, [activeSection, fetchTokens]);

    // Fetch Logs
    const fetchLogs = useCallback(async () => {
        setLoadingLogs(true);
        try {
            const res = await fetch(`${API_BASE}/api-proxy/logs?limit=200`);
            if (res.ok) {
                const data = await res.json();
                setLogs(data.items || []);
            }
        } catch { }
        finally { setLoadingLogs(false); }
    }, []);

    // Fetch Model Mappings
    const fetchMappings = useCallback(async () => {
        setLoadingMappings(true);
        try {
            const res = await fetch(`${API_BASE}/model-mappings/`);
            if (res.ok) {
                const data = await res.json();
                setMappings(data.items || []);
            }
        } catch { }
        finally { setLoadingMappings(false); }
    }, []);

    useEffect(() => {
        if (activeSection === "logs") {
            fetchLogs();
            const interval = setInterval(fetchLogs, 5000);
            return () => clearInterval(interval);
        }
    }, [activeSection, fetchLogs]);

    useEffect(() => {
        if (activeSection === "models") {
            fetchMappings();
        }
    }, [activeSection, fetchMappings]);

    const handleStart = async () => {
        setActing(true);
        try {
            await fetch(`${API_BASE}/api-proxy/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    port: parseInt(port) || 9090,
                    upstream,
                }),
            });
            await fetchStatus();
        } catch { /* ignore */ }
        finally { setActing(false); }
    };

    const handleStop = async () => {
        setActing(true);
        try {
            await fetch(`${API_BASE}/api-proxy/stop`, { method: "POST" });
            await fetchStatus();
        } catch { /* ignore */ }
        finally { setActing(false); }
    };

    const handleRefreshPool = async () => {
        setRefreshingPool(true);
        try {
            await fetch(`${API_BASE}/api-proxy/refresh-pool`, { method: "POST" });
            await fetchStatus();
        } catch { /* ignore */ }
        finally { setRefreshingPool(false); }
    };

    const savePoolSetting = async (key: string, value: string) => {
        try {
            await fetch(`${API_BASE}/settings/`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify([{ key, value }]),
            });
        } catch { /* ignore */ }
    };

    const handleScheduleModeChange = (value: string) => {
        setScheduleMode(value);
        savePoolSetting("pool_schedule_mode", value);
    };

    const handleCooldownChange = (value: string) => {
        setPoolCooldown(value);
        savePoolSetting("pool_cooldown", value);
    };

    const copyUrl = async () => {
        const url = `http://127.0.0.1:${status?.port || port}`;
        await navigator.clipboard.writeText(url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const isRunning = status?.running ?? false;

    // Token Actions
    const handleCreateToken = async () => {
        if (!newTokenName.trim()) return;
        setCreatingToken(true);
        try {
            const res = await fetch(`${API_BASE}/api-tokens/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: newTokenName.trim() })
            });
            if (res.ok) {
                const data = await res.json();
                setNewlyGeneratedToken(data.token);
                setDialogType("create");
                setIsTokenDialogOpen(true);
                setNewTokenName("");
                fetchTokens();
            }
        } catch { }
        finally { setCreatingToken(false); }
    };

    const handleDeleteToken = (id: number) => {
        setConfirmDialog({ isOpen: true, type: "delete", tokenId: id });
    };

    const handleToggleToken = async (id: number) => {
        try {
            await fetch(`${API_BASE}/api-tokens/${id}/toggle`, { method: "PATCH" });
            fetchTokens();
        } catch { }
    };

    const handleRegenerateToken = (id: number) => {
        setConfirmDialog({ isOpen: true, type: "regenerate", tokenId: id });
    };

    const handleConfirmAction = async () => {
        const id = confirmDialog.tokenId;
        if (!id) return;

        setIsConfirming(true);
        try {
            if (confirmDialog.type === "delete") {
                await fetch(`${API_BASE}/api-tokens/${id}`, { method: "DELETE" });
                setConfirmDialog({ ...confirmDialog, isOpen: false });
                fetchTokens();
            } else if (confirmDialog.type === "regenerate") {
                const res = await fetch(`${API_BASE}/api-tokens/${id}/regenerate`, { method: "POST" });
                if (res.ok) {
                    const data = await res.json();
                    setNewlyGeneratedToken(data.token);
                    setDialogType("regenerate");
                    setIsTokenDialogOpen(true);
                    setConfirmDialog({ ...confirmDialog, isOpen: false });
                    fetchTokens();
                }
            }
        } catch { }
        finally { setIsConfirming(false); }
    };

    const handleCopyModelId = (id: string) => {
        navigator.clipboard.writeText(id).catch(() => { });
        setCopiedModelId(id);
        setTimeout(() => {
            setCopiedModelId(curr => (curr === id ? null : curr));
        }, 2000);
    };

    // Model Mapping CRUD
    const handleAddMappingInline = () => {
        setEditingId("__new__");
        setEditPattern("");
        setEditTarget("");
    };

    const handleEditMappingInline = (mapping: ModelMappingRule) => {
        setEditingId(mapping.id);
        setEditPattern(mapping.pattern);
        setEditTarget(mapping.target);
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditPattern("");
        setEditTarget("");
    };

    const handleSaveMapping = async () => {
        if (!editPattern.trim() || !editTarget.trim()) return;
        setSavingMapping(true);
        try {
            if (editingId === "__new__") {
                const nextPriority = mappings.length > 0 ? Math.max(...mappings.map(m => m.priority)) + 1 : 0;
                await fetch(`${API_BASE}/model-mappings/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ pattern: editPattern.trim(), target: editTarget.trim(), priority: nextPriority }),
                });
            } else {
                await fetch(`${API_BASE}/model-mappings/${editingId}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ pattern: editPattern.trim(), target: editTarget.trim() }),
                });
            }
            setEditingId(null);
            fetchMappings();
        } catch { }
        finally { setSavingMapping(false); }
    };

    const handleToggleMapping = async (id: string) => {
        const mapping = mappings.find(m => m.id === id);
        if (!mapping) return;
        try {
            await fetch(`${API_BASE}/model-mappings/${id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: !mapping.is_active }),
            });
            fetchMappings();
        } catch { }
    };

    const handleDeleteMapping = async () => {
        const id = deleteMappingConfirm.id;
        if (!id) return;
        try {
            await fetch(`${API_BASE}/model-mappings/${id}`, { method: "DELETE" });
            setDeleteMappingConfirm({ isOpen: false, id: null });
            fetchMappings();
        } catch { }
    };

    const handleDragEnd = async (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const oldIndex = mappings.findIndex(m => m.id === active.id);
        const newIndex = mappings.findIndex(m => m.id === over.id);
        if (oldIndex === -1 || newIndex === -1) return;
        const reordered = arrayMove(mappings, oldIndex, newIndex);
        setMappings(reordered);
        try {
            await fetch(`${API_BASE}/model-mappings/reorder`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items: reordered.map((m, i) => ({ id: m.id, priority: i })) }),
            });
        } catch { fetchMappings(); }
    };

    const handleViewTokenUsage = async (tokenId: number) => {
        setUsageTokenId(tokenId);
        setLoadingUsage(true);
        try {
            const res = await fetch(`${API_BASE}/api-proxy/logs?limit=200`);
            if (res.ok) {
                const data = await res.json();
                setUsageLogs(data.items || []);
            }
        } catch { }
        finally { setLoadingUsage(false); }
    };

    const activeInfo = sections.find((s) => s.id === activeSection)!;

    return (
        <div className="-m-6 flex h-[calc(100%+48px)] overflow-hidden animate-in fade-in duration-500">
            {/* Left Nav Panel */}
            <div className="w-[260px] shrink-0 bg-background border-r border-border overflow-y-auto rounded-l-xl">
                <div className="flex items-center justify-between px-5 py-5">
                    <h1 className="text-base font-semibold">{t("title")}</h1>
                </div>
                <nav className="space-y-0.5 px-3 pb-4">
                    {sections.map((section) => {
                        const Icon = section.icon;
                        return (
                            <button
                                key={section.id}
                                onClick={() => setActiveSection(section.id)}
                                className={cn(
                                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                                    activeSection === section.id
                                        ? "bg-neutral-200/70 text-foreground dark:bg-white/6"
                                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground dark:hover:bg-white/5"
                                )}
                            >
                                <Icon className="h-4 w-4 shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <div className="text-[13px] font-medium leading-none">{t(section.labelKey)}</div>
                                        {section.id === "proxy" && (
                                            <div
                                                className={cn(
                                                    "h-1.5 w-1.5 rounded-full shrink-0 transition-colors",
                                                    isRunning ? "bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.4)]" : "bg-neutral-300 dark:bg-neutral-600"
                                                )}
                                            />
                                        )}
                                    </div>
                                    <div className="text-[11px] text-muted-foreground truncate mt-1">
                                        {t(section.descKey)}
                                    </div>
                                </div>
                            </button>
                        );
                    })}
                </nav>
            </div>

            {/* Right Content Panel */}
            <div className="flex-1 min-w-0 overflow-y-auto bg-muted/30 dark:bg-muted/20">
                <div className="px-8 py-6 w-full max-w-5xl mx-auto">
                    <h2 className="text-base font-semibold text-center">{t(activeInfo.labelKey)}</h2>
                </div>

                <div className="px-8 pb-8 space-y-6 w-full max-w-5xl mx-auto flex-1 flex flex-col">
                    {/* Antigravity Proxy Content */}
                    {activeSection === "proxy" && (
                        <div className="space-y-6">

                            {/* Status Banner */}
                            <div className="space-y-2">
                                <h3 className="text-sm font-semibold">{t("status")}</h3>
                                <div className={cn(
                                "rounded-lg border p-4 flex items-center gap-4 transition-colors relative overflow-hidden",
                                isRunning
                                    ? "border-emerald-500/30 bg-emerald-500/5"
                                    : "border-border bg-card",
                                showShine && "animate-card-shine"
                            )}>
                                <div className={cn(
                                    "flex h-10 w-10 items-center justify-center rounded-full",
                                    isRunning ? "bg-emerald-500/10" : "bg-muted/50"
                                )}>
                                    <Network className={cn(
                                        "h-5 w-5",
                                        isRunning ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"
                                    )} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-sm">{t("status")}</span>
                                        <Badge
                                            variant={isRunning ? "default" : "secondary"}
                                            className={cn(
                                                "text-[10px] h-5",
                                                isRunning ? "bg-emerald-600 hover:bg-emerald-600" : ""
                                            )}
                                        >
                                            {isRunning ? t("running") : t("stopped")}
                                        </Badge>
                                    </div>
                                    {isRunning && (
                                        <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                                            http://127.0.0.1:{status?.port}
                                        </p>
                                    )}
                                </div>
                                {isRunning && (
                                    <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
                                        <div className="text-center">
                                            <div className="font-bold text-foreground text-base tabular-nums">{status?.total_requests ?? 0}</div>
                                            <div>{t("totalRequests")}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="font-bold text-foreground text-base tabular-nums">{formatUptime(status?.started_at ?? null)}</div>
                                            <div>{t("uptime")}</div>
                                        </div>
                                    </div>
                                )}

                                <Button
                                    size="icon"
                                    className={cn(
                                        "h-8 w-8 rounded-full shrink-0 shadow-sm transition-all relative overflow-hidden ml-2",
                                        isRunning
                                            ? "bg-red-500 hover:bg-red-600 text-white dark:bg-red-600/90"
                                            : "bg-emerald-500 hover:bg-emerald-600 text-white dark:bg-emerald-600/90"
                                    )}
                                    onClick={isRunning ? handleStop : handleStart}
                                    disabled={acting}
                                    title={isRunning ? t("stop") : t("start")}
                                >
                                    {acting ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : isRunning ? (
                                        <Square className="h-3 w-3" fill="currentColor" />
                                    ) : (
                                        <Play className="h-3 w-3 ml-0.5" fill="currentColor" />
                                    )}
                                </Button>
                            </div>
                            </div>

                            {/* Configuration */}
                            <div className="space-y-2">
                                <h3 className="text-sm font-semibold">{t("configuration")}</h3>
                                <div className="rounded-lg border border-border bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none divide-y divide-border">
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("port")}</Label>
                                            <p className="text-[11px] text-muted-foreground mt-0.5">{t("portDesc")}</p>
                                        </div>
                                        <Input
                                            className="w-24 h-8 text-xs text-center font-mono"
                                            value={port}
                                            onChange={(e) => setPort(e.target.value)}
                                            disabled={isRunning}
                                            type="number"
                                        />
                                    </div>

                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("upstream")}</Label>
                                        </div>
                                        <Select
                                            value={upstream}
                                            onValueChange={setUpstream}
                                            disabled={isRunning}
                                        >
                                            <SelectTrigger className="w-52 h-8 text-xs">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="https://daily-cloudcode-pa.googleapis.com" className="text-xs">
                                                    {t("upstreamDaily")}
                                                </SelectItem>
                                                <SelectItem value="https://cloudcode-pa.googleapis.com" className="text-xs">
                                                    {t("upstreamProd")}
                                                </SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>

                            {/* Account Pool */}
                            <div className="space-y-2">
                                <h3 className="text-sm font-semibold">{t("pool")}</h3>
                                <div className="rounded-lg border border-border bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none divide-y divide-border">
                                    {/* Pool Summary + Active Accounts */}
                                    <div className="px-4 py-3.5">
                                        <button
                                            className="flex items-center justify-between w-full text-left"
                                            onClick={() => setPoolExpanded(!poolExpanded)}
                                        >
                                            <div className="flex items-center gap-2">
                                                <Users className="h-4 w-4 text-muted-foreground" />
                                                <span className="text-[13px] font-medium">{t("activeAccounts" as any)}</span>
                                                {(status?.pool_accounts?.length ?? 0) > 0 && (
                                                    <ChevronRight className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform duration-200", poolExpanded && "rotate-90")} />
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                {(status?.pool_size ?? 0) > 0 ? (
                                                    <>
                                                        <Badge variant="secondary" className="text-[10px] font-normal">
                                                            {t("poolSize", { count: status?.pool_size ?? 0 })}
                                                        </Badge>
                                                        <Badge variant="outline" className="text-[10px] font-normal text-emerald-600 dark:text-emerald-400 border-emerald-500/30">
                                                            {t("poolAvailable", { count: status?.pool_available ?? 0 })}
                                                        </Badge>
                                                    </>
                                                ) : (
                                                    <span className="text-xs text-muted-foreground italic">{t("poolEmpty")}</span>
                                                )}
                                            </div>
                                        </button>
                                        {poolExpanded && (status?.pool_accounts?.length ?? 0) > 0 && (
                                            <div className="space-y-1.5 mt-3 pt-3 border-t border-border/50 animate-in slide-in-from-top-1 duration-150">
                                                {status?.pool_accounts?.map((acc) => (
                                                    <div key={acc.id} className="flex items-center justify-between py-1">
                                                        <span className="text-xs font-mono text-muted-foreground">{acc.email}</span>
                                                        <div className="flex items-center gap-1.5">
                                                            {acc.status === "available" && (
                                                                <Badge variant="outline" className="text-[9px] h-5 px-1.5 text-emerald-600 border-emerald-500/30 bg-emerald-500/5">
                                                                    {t("accountAvailable" as any)}
                                                                </Badge>
                                                            )}
                                                            {acc.status === "rate_limited" && (
                                                                <Badge variant="outline" className="text-[9px] h-5 px-1.5 text-amber-600 border-amber-500/30 bg-amber-500/5">
                                                                    {t("accountRateLimited" as any)} {acc.remaining_seconds != null && `(${acc.remaining_seconds}s)`}
                                                                </Badge>
                                                            )}
                                                            {acc.status === "exhausted" && (
                                                                <Badge variant="outline" className="text-[9px] h-5 px-1.5 text-red-600 border-red-500/30 bg-red-500/5">
                                                                    {t("accountExhausted" as any)}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    {/* Schedule Mode */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("scheduleMode" as any)}</Label>
                                            <p className="text-[11px] text-muted-foreground mt-0.5">
                                                {scheduleMode === "cache_first" && t("scheduleCacheFirstDesc" as any)}
                                                {scheduleMode === "balance" && t("scheduleBalanceDesc" as any)}
                                                {scheduleMode === "performance" && t("schedulePerformanceDesc" as any)}
                                            </p>
                                        </div>
                                        <Select value={scheduleMode} onValueChange={handleScheduleModeChange}>
                                            <SelectTrigger className="w-40 h-8 text-xs">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="cache_first" className="text-xs">{t("scheduleCacheFirst" as any)}</SelectItem>
                                                <SelectItem value="balance" className="text-xs">{t("scheduleBalance" as any)}</SelectItem>
                                                <SelectItem value="performance" className="text-xs">{t("schedulePerformance" as any)}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Request Cooldown */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("requestCooldown" as any)}</Label>
                                            <p className="text-[11px] text-muted-foreground mt-0.5">{t("requestCooldownDesc" as any)}</p>
                                        </div>
                                        <Select value={poolCooldown} onValueChange={handleCooldownChange}>
                                            <SelectTrigger className="w-24 h-8 text-xs">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="0" className="text-xs">{t("cooldownNone" as any)}</SelectItem>
                                                <SelectItem value="1" className="text-xs">1{t("cooldownSeconds" as any)}</SelectItem>
                                                <SelectItem value="2" className="text-xs">2{t("cooldownSeconds" as any)}</SelectItem>
                                                <SelectItem value="3" className="text-xs">3{t("cooldownSeconds" as any)}</SelectItem>
                                                <SelectItem value="4" className="text-xs">4{t("cooldownSeconds" as any)}</SelectItem>
                                                <SelectItem value="5" className="text-xs">5{t("cooldownSeconds" as any)}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Models & Mapping Content */}
                    {activeSection === "models" && (
                        <div className="space-y-6">
                            {/* Mapping Rules — FIRST */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h3 className="text-sm font-semibold">{t("mappingRules" as any)}</h3>
                                        <p className="text-[11px] text-muted-foreground mt-0.5">{t("wildcardHint" as any)}</p>
                                    </div>
                                    <Button
                                        size="sm"
                                        className="h-7 gap-1.5 text-xs"
                                        onClick={handleAddMappingInline}
                                        disabled={editingId === "__new__"}
                                    >
                                        <Plus className="h-3 w-3" />
                                        {t("addRule" as any)}
                                    </Button>
                                </div>

                                <div className="rounded-lg border border-border bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none overflow-hidden text-xs">
                                    <div className="grid grid-cols-[24px_1fr_32px_1fr_60px_80px] gap-2 border-b border-border/50 px-4 py-2 font-medium text-muted-foreground uppercase tracking-wider text-[10px] bg-muted/20">
                                        <div></div>
                                        <div>{t("mappingPattern" as any)}</div>
                                        <div></div>
                                        <div>{t("mappingTarget" as any)}</div>
                                        <div>{t("status")}</div>
                                        <div className="text-right">{c("confirm") === "Confirm" ? "Actions" : "操作"}</div>
                                    </div>
                                    <div className="divide-y divide-border/50">
                                        {/* New rule row */}
                                        {editingId === "__new__" && (
                                            <div className="grid grid-cols-[24px_1fr_32px_1fr_60px_80px] gap-2 px-4 py-2 items-center bg-primary/5 border-l-2 border-l-primary">
                                                <div />
                                                <div>
                                                    <Input
                                                        placeholder={t("mappingPatternPlaceholder" as any)}
                                                        value={editPattern}
                                                        onChange={e => setEditPattern(e.target.value)}
                                                        className="h-7 text-[11px] font-mono"
                                                        autoFocus
                                                        onKeyDown={e => { if (e.key === "Enter") handleSaveMapping(); if (e.key === "Escape") handleCancelEdit(); }}
                                                    />
                                                </div>
                                                <div className="flex justify-center">
                                                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                                                </div>
                                                <div>
                                                    <Select value={editTarget} onValueChange={setEditTarget}>
                                                        <SelectTrigger className="h-7 text-[11px] font-mono">
                                                            <SelectValue placeholder={t("mappingTargetPlaceholder" as any)} />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {AVAILABLE_MODELS.map(m => (
                                                                <SelectItem key={m.id} value={m.id} className="text-xs font-mono">
                                                                    {m.id}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <div></div>
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button variant="ghost" size="icon" className="h-6 w-6 text-emerald-600" onClick={handleSaveMapping} disabled={!editPattern.trim() || !editTarget.trim() || savingMapping}>
                                                        {savingMapping ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                                                    </Button>
                                                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCancelEdit}>
                                                        <Square className="h-2.5 w-2.5" />
                                                    </Button>
                                                </div>
                                            </div>
                                        )}

                                        {/* Existing rules with drag-and-drop */}
                                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                                            <SortableContext items={mappings.map(m => m.id)} strategy={verticalListSortingStrategy}>
                                                {mappings.map(mapping => (
                                                    <SortableMappingRow
                                                        key={mapping.id}
                                                        mapping={mapping}
                                                        editingId={editingId}
                                                        editPattern={editPattern}
                                                        setEditPattern={setEditPattern}
                                                        editTarget={editTarget}
                                                        setEditTarget={setEditTarget}
                                                        handleSaveMapping={handleSaveMapping}
                                                        handleCancelEdit={handleCancelEdit}
                                                        savingMapping={savingMapping}
                                                        handleEditMappingInline={handleEditMappingInline}
                                                        handleToggleMapping={handleToggleMapping}
                                                        setDeleteMappingConfirm={setDeleteMappingConfirm}
                                                        t={t}
                                                        MODELS={AVAILABLE_MODELS}
                                                    />
                                                ))}
                                            </SortableContext>
                                        </DndContext>

                                        {/* Empty state (only when no rules AND not adding new) */}
                                        {mappings.length === 0 && editingId !== "__new__" && (
                                            <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
                                                <ArrowRight className="h-6 w-6 text-muted-foreground/40 mb-2" />
                                                <p className="text-xs font-medium">{t("noMappingRules" as any)}</p>
                                                <p className="text-[11px] text-muted-foreground/70 mt-0.5">{t("noMappingRulesDesc" as any)}</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Available Models — SECOND */}
                            <div className="space-y-2">
                                <h3 className="text-sm font-semibold flex items-center gap-1.5">
                                    {t("models")}
                                </h3>
                                <div className="rounded-lg border border-border bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none overflow-hidden text-xs">
                                    <div className="grid grid-cols-[180px_240px_1fr] gap-2 border-b border-border/50 px-4 py-2 font-medium text-muted-foreground uppercase tracking-wider text-[10px] bg-muted/20">
                                        <div>{t("modelName" as any)}</div>
                                        <div>{t("modelId" as any)}</div>
                                        <div>{t("modelDesc" as any)}</div>
                                    </div>
                                    <div className="divide-y divide-border/50">
                                        {AVAILABLE_MODELS.map(model => (
                                            <div key={model.id} className="group grid grid-cols-[180px_240px_1fr] gap-2 px-4 py-2.5 items-center hover:bg-muted/30 transition-colors">
                                                <div className="font-medium flex items-center gap-1.5">
                                                    {model.name}
                                                </div>
                                                <div className="font-mono text-[11px] text-muted-foreground flex items-center">
                                                    <span className="bg-muted px-1.5 py-0.5 rounded border border-border/50">
                                                        {model.id}
                                                    </span>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className={cn(
                                                            "h-4 w-4 ml-1.5 shrink-0 transition-opacity",
                                                            copiedModelId === model.id ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus:opacity-100"
                                                        )}
                                                        onClick={() => handleCopyModelId(model.id)}
                                                    >
                                                        {copiedModelId === model.id ? (
                                                            <Check className="h-2.5 w-2.5 text-emerald-500" />
                                                        ) : (
                                                            <Copy className="h-2.5 w-2.5 text-muted-foreground" />
                                                        )}
                                                    </Button>
                                                </div>
                                                <div className="text-muted-foreground truncate" title={t(model.descKey as any)}>
                                                    {t(model.descKey as any)}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Token Management Content */}
                    {activeSection === "tokens" && (
                        <div className="space-y-6">
                            {/* Create Token */}
                            <div className="flex items-end gap-2">
                                <div className="flex-1 space-y-1.5">
                                    <Label className="text-[13px] font-medium">{t("createToken")}</Label>
                                    <Input
                                        placeholder={t("tokenNamePlaceholder")}
                                        value={newTokenName}
                                        onChange={e => setNewTokenName(e.target.value)}
                                        className="h-9 text-xs"
                                        onKeyDown={e => e.key === "Enter" && handleCreateToken()}
                                    />
                                </div>
                                <Button
                                    onClick={handleCreateToken}
                                    disabled={!newTokenName.trim() || creatingToken}
                                    className="h-9 text-xs px-4"
                                >
                                    {creatingToken ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Plus className="h-4 w-4 mr-1.5" />}
                                    {t("createToken")}
                                </Button>
                            </div>

                            {/* Token List */}
                            <div className="space-y-3">
                                {loadingTokens && tokens.length === 0 ? (
                                    <div className="text-center py-8 text-muted-foreground">
                                        <Loader2 className="h-5 w-5 animate-spin mx-auto" />
                                    </div>
                                ) : tokens.length === 0 ? (
                                    <div className="rounded-lg border border-border bg-card p-8 text-center shadow-sm">
                                        <KeyRound className="h-8 w-8 text-muted-foreground/50 mx-auto mb-3" />
                                        <h3 className="text-sm font-semibold mb-1">{t("noTokens")}</h3>
                                        <p className="text-xs text-muted-foreground">{t("noTokensDesc")}</p>
                                    </div>
                                ) : (
                                    tokens.map(token => (
                                        <div key={token.id} className="rounded-lg border border-border bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 flex flex-col gap-3">
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-semibold text-sm">{token.name}</span>
                                                    <Badge variant={token.is_active ? "default" : "secondary"} className={cn("text-[10px] h-5", token.is_active && "bg-emerald-600 hover:bg-emerald-600")}>
                                                        {token.is_active ? t("tokenEnabled") : t("tokenDisabled")}
                                                    </Badge>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <Switch
                                                        checked={token.is_active}
                                                        onCheckedChange={() => handleToggleToken(token.id)}
                                                    />
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2">
                                                <code className="bg-muted/50 rounded px-2.5 py-1.5 font-mono text-xs text-muted-foreground flex-1 border border-border/50">
                                                    {token.token}
                                                </code>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7 shrink-0"
                                                    onClick={async () => {
                                                        await navigator.clipboard.writeText(token.token);
                                                        setCopiedModelId(`token-${token.id}`);
                                                        setTimeout(() => setCopiedModelId(curr => curr === `token-${token.id}` ? null : curr), 2000);
                                                    }}
                                                >
                                                    {copiedModelId === `token-${token.id}` ? (
                                                        <Check className="h-3.5 w-3.5 text-emerald-500" />
                                                    ) : (
                                                        <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                                                    )}
                                                </Button>
                                            </div>

                                            <div className="flex items-center justify-between mt-1 pt-3 border-t border-border/50">
                                                <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                                                    <div className="flex items-center gap-1.5">
                                                        <Clock className="h-3.5 w-3.5 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{new Date(token.created_at).toLocaleDateString()}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5">
                                                        <Zap className="h-3.5 w-3.5 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{t("totalTokenRequests")}: {token.total_requests}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5">
                                                        <Power className="h-3.5 w-3.5 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{t("lastUsed")}: {token.last_used_at ? new Date(token.last_used_at).toLocaleDateString() : t("never")}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1">
                                                    <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => handleViewTokenUsage(token.id)}>
                                                        <BarChart3 className="h-3 w-3 mr-1 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{t("usageDetails" as any)}</span>
                                                    </Button>
                                                    <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => handleRegenerateToken(token.id)}>
                                                        <RefreshCw className="h-3 w-3 mr-1 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{t("regenerateToken")}</span>
                                                    </Button>
                                                    <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px] text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30" onClick={() => handleDeleteToken(token.id)}>
                                                        <Trash2 className="h-3 w-3 mr-1 shrink-0" />
                                                        <span className="mt-[1px] leading-none">{t("deleteToken")}</span>
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>


                        </div>
                    )}

                    {/* Proxy Logs Content */}
                    {activeSection === "logs" && (
                        <div className="space-y-4">
                            {/* Header */}
                            <div className="flex items-center justify-between">
                                <p className="text-sm text-muted-foreground">{t("proxyLogsSubtitle")}</p>
                                <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loadingLogs} className="gap-1.5 h-8 text-xs">
                                    <RefreshCcw className={cn("h-3.5 w-3.5", loadingLogs && "animate-spin")} />
                                    {c("refresh")}
                                </Button>
                            </div>

                            {/* Log Table */}
                            <div className="rounded-lg border border-border bg-card overflow-hidden text-xs shadow-sm">
                                {/* Table Header */}
                                <div className="grid grid-cols-[50px_70px_1fr_70px_60px_70px_60px] gap-2 border-b border-border px-4 py-2 font-medium text-muted-foreground uppercase tracking-wider text-[10px] bg-card">
                                    <div>{t("logMethod")}</div>
                                    <div>Format</div>
                                    <div>Model</div>
                                    <div>Account</div>
                                    <div>{t("logStatus")}</div>
                                    <div>{t("logTime")}</div>
                                    <div className="text-right">{t("logDuration")}</div>
                                </div>

                                {/* Table Body */}
                                <div className="divide-y divide-border/60 bg-card max-h-[500px] overflow-y-auto">
                                    {!loadingLogs && logs.length === 0 && (
                                        <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                                            <Inbox className="h-8 w-8 text-muted-foreground/40 mb-3" />
                                            <p className="text-sm font-medium">{t("noLogs")}</p>
                                            <p className="text-xs text-muted-foreground/70 mt-1">{t("noLogsDesc")}</p>
                                        </div>
                                    )}

                                    {logs.map((log) => (
                                        <div key={log.id} className="group transition-colors">
                                            <div
                                                className={cn(
                                                    "grid grid-cols-[50px_70px_1fr_70px_60px_70px_60px] gap-2 px-4 py-2.5 items-center hover:bg-muted/40 transition-colors cursor-pointer border-l-2 border-l-transparent",
                                                    expandedLogId === log.id ? "bg-muted/40 border-l-primary" : "hover:border-l-muted-foreground/30"
                                                )}
                                                onClick={() => setExpandedLogId(prev => (prev === log.id ? null : log.id))}
                                            >
                                                <div>
                                                    <Badge variant="outline" className={cn(
                                                        "font-mono text-[9px] uppercase font-bold px-1.5 py-0 h-5",
                                                        "text-emerald-500 border-emerald-500/20 bg-emerald-500/5",
                                                    )}>
                                                        {log.method}
                                                    </Badge>
                                                </div>
                                                <div>
                                                    <Badge variant="outline" className={cn(
                                                        "text-[9px] px-1.5 py-0 h-5 font-medium",
                                                        log.api_format === "openai" ? "text-blue-500 border-blue-500/20 bg-blue-500/5" : "text-orange-500 border-orange-500/20 bg-orange-500/5"
                                                    )}>
                                                        {log.api_format === "openai" ? "OpenAI" : "Anthropic"}
                                                    </Badge>
                                                </div>
                                                <div className="font-mono text-[11px] truncate text-foreground/90" title={log.model}>
                                                    {log.original_model ? (
                                                        <span>
                                                            <span className="text-muted-foreground/60">{log.original_model}</span>
                                                            <span className="text-muted-foreground/40 mx-1">→</span>
                                                            {log.model}
                                                        </span>
                                                    ) : log.model}
                                                    {log.stream && <span className="text-muted-foreground/60 ml-1">(stream)</span>}
                                                </div>
                                                <div className="font-mono text-[10px] text-muted-foreground/80 truncate" title={log.account_email}>
                                                    {log.account_email ? log.account_email.split("@")[0] : "—"}
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
                                                <div className="font-mono text-[10px] text-muted-foreground/80">
                                                    {log.timestamp_iso ? new Date(log.timestamp_iso).toLocaleTimeString() : "—"}
                                                </div>
                                                <div className="text-right font-mono text-[11px] text-muted-foreground">
                                                    {log.duration_ms.toFixed(0)}ms
                                                </div>
                                            </div>

                                            {/* Expanded Detail */}
                                            {expandedLogId === log.id && (
                                                <div className="bg-card border-b border-border/60 px-4 py-4 animate-in slide-in-from-top-1 duration-200">
                                                    <div className="grid grid-cols-2 gap-4">
                                                        <div className="space-y-2 border rounded-md p-3 bg-background/60">
                                                            <h3 className="font-semibold text-xs flex items-center gap-2">
                                                                <span className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[10px] uppercase font-bold">INFO</span>
                                                                {t("logPath")}: {log.path}
                                                            </h3>
                                                            <div className="space-y-1.5 text-[11px]">
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Format:</span>
                                                                    <span className="font-medium">{log.api_format === "openai" ? "OpenAI" : "Anthropic"}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Model:</span>
                                                                    <span className="font-mono">{log.model}</span>
                                                                </div>
                                                                {log.original_model && (
                                                                    <div className="flex justify-between">
                                                                        <span className="text-muted-foreground">{t("originalModel" as any)}:</span>
                                                                        <span className="font-mono">{log.original_model}</span>
                                                                    </div>
                                                                )}
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Stream:</span>
                                                                    <span>{log.stream ? "Yes" : "No"}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Account:</span>
                                                                    <span className="font-mono">{log.account_email || "—"}</span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="space-y-2 border rounded-md p-3 bg-background/60">
                                                            <h3 className="font-semibold text-xs flex items-center gap-2">
                                                                <span className={cn(
                                                                    "px-1.5 py-0.5 rounded text-[10px] uppercase font-bold",
                                                                    log.status_code >= 400 ? "bg-destructive/10 text-destructive" : "bg-emerald-500/10 text-emerald-600"
                                                                )}>RES</span>
                                                                Response
                                                            </h3>
                                                            {log.error && (
                                                                <div className="bg-destructive/10 text-destructive p-2 rounded text-[10px] font-mono mb-2 border border-destructive/20">
                                                                    <span className="font-bold">Error:</span> {log.error}
                                                                </div>
                                                            )}
                                                            <div className="space-y-1.5 text-[11px]">
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Status:</span>
                                                                    <span className="font-mono font-bold">{log.status_code}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Duration:</span>
                                                                    <span className="font-mono">{log.duration_ms.toFixed(0)}ms</span>
                                                                </div>
                                                                {(log.input_tokens > 0 || log.output_tokens > 0) && (
                                                                    <>
                                                                        <div className="flex justify-between">
                                                                            <span className="text-muted-foreground">Input Tokens:</span>
                                                                            <span className="font-mono">{log.input_tokens.toLocaleString()}</span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                            <span className="text-muted-foreground">Output Tokens:</span>
                                                                            <span className="font-mono">{log.output_tokens.toLocaleString()}</span>
                                                                        </div>
                                                                    </>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Token Copy Dialog */}
            <Dialog open={isTokenDialogOpen} onOpenChange={setIsTokenDialogOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>
                            {dialogType === "create" ? t("tokenCreated") : t("tokenRegenerated")}
                        </DialogTitle>
                        <DialogDescription>
                            {t("tokenCreatedDesc")}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="flex items-center space-x-2 my-2">
                        <Input
                            readOnly
                            value={newlyGeneratedToken || ""}
                            className="font-mono text-xs bg-muted/50 h-9"
                        />
                        <Button
                            size="sm"
                            className="shrink-0 h-9 px-3"
                            onClick={async () => {
                                if (newlyGeneratedToken) {
                                    await navigator.clipboard.writeText(newlyGeneratedToken);
                                    setCopied(true);
                                    setTimeout(() => setCopied(false), 2000);
                                }
                            }}
                        >
                            {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                        </Button>
                    </div>
                    <DialogFooter>
                        <Button type="button" onClick={() => setIsTokenDialogOpen(false)}>
                            {c("close")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Action Confirm Dialog */}
            <Dialog open={confirmDialog.isOpen} onOpenChange={(open) => setConfirmDialog(prev => ({ ...prev, isOpen: open }))}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>
                            {confirmDialog.type === "delete" ? t("deleteToken") : t("regenerateToken")}
                        </DialogTitle>
                        <DialogDescription>
                            {confirmDialog.type === "delete" ? t("deleteTokenConfirm") : t("regenerateTokenConfirm")}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="mt-4">
                        <Button
                            variant="outline"
                            onClick={() => setConfirmDialog(prev => ({ ...prev, isOpen: false }))}
                            disabled={isConfirming}
                        >
                            {c("cancel")}
                        </Button>
                        <Button
                            variant={confirmDialog.type === "delete" ? "destructive" : "default"}
                            onClick={handleConfirmAction}
                            disabled={isConfirming}
                        >
                            {isConfirming && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {confirmDialog.type === "delete" ? t("deleteToken") : t("regenerateToken")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Mapping Delete Confirm Dialog */}
            <Dialog open={deleteMappingConfirm.isOpen} onOpenChange={(open) => setDeleteMappingConfirm(prev => ({ ...prev, isOpen: open }))}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{t("deleteRule" as any)}</DialogTitle>
                        <DialogDescription>{t("deleteRuleConfirm" as any)}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setDeleteMappingConfirm({ isOpen: false, id: null })}>
                            {c("cancel")}
                        </Button>
                        <Button variant="destructive" onClick={handleDeleteMapping}>
                            {t("deleteRule" as any)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Token Usage Details Dialog */}
            <Dialog open={usageTokenId !== null} onOpenChange={(open) => { if (!open) setUsageTokenId(null); }}>
                <DialogContent className="sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <BarChart3 className="h-4 w-4" />
                            {t("usageDetails" as any)}
                            {usageTokenId && (
                                <Badge variant="secondary" className="text-[10px] font-normal ml-1">
                                    {tokens.find(t => t.id === usageTokenId)?.name}
                                </Badge>
                            )}
                        </DialogTitle>
                        <DialogDescription>{t("usageDetailsDesc" as any)}</DialogDescription>
                    </DialogHeader>
                    {loadingUsage ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {(() => {
                                const token = tokens.find(t => t.id === usageTokenId);
                                if (!token) return null;
                                const totalInputTokens = usageLogs.reduce((sum, l) => sum + (l.input_tokens || 0), 0);
                                const totalOutputTokens = usageLogs.reduce((sum, l) => sum + (l.output_tokens || 0), 0);
                                return (
                                    <>
                                        <div className="grid grid-cols-3 gap-3">
                                            <div className="rounded-lg border border-border bg-muted/30 p-3 text-center">
                                                <div className="text-2xl font-bold tabular-nums">{token.total_requests}</div>
                                                <div className="text-[11px] text-muted-foreground mt-1">{t("totalTokenRequests")}</div>
                                            </div>
                                            <div className="rounded-lg border border-border bg-muted/30 p-3 text-center">
                                                <div className="text-2xl font-bold tabular-nums text-blue-600">{totalInputTokens.toLocaleString()}</div>
                                                <div className="text-[11px] text-muted-foreground mt-1">{t("inputTokens" as any)}</div>
                                            </div>
                                            <div className="rounded-lg border border-border bg-muted/30 p-3 text-center">
                                                <div className="text-2xl font-bold tabular-nums text-emerald-600">{totalOutputTokens.toLocaleString()}</div>
                                                <div className="text-[11px] text-muted-foreground mt-1">{t("outputTokens" as any)}</div>
                                            </div>
                                        </div>
                                        <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2 text-xs">
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">{t("createToken")}:</span>
                                                <span className="font-mono">{new Date(token.created_at).toLocaleString()}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">{t("lastUsed")}:</span>
                                                <span className="font-mono">{token.last_used_at ? new Date(token.last_used_at).toLocaleString() : t("never")}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">{t("totalTokens" as any)}:</span>
                                                <span className="font-mono font-bold">{(totalInputTokens + totalOutputTokens).toLocaleString()}</span>
                                            </div>
                                        </div>
                                    </>
                                );
                            })()}
                        </div>
                    )}
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setUsageTokenId(null)}>
                            {c("close")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
