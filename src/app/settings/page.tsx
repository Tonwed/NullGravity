"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import {
    Sun,
    Moon,
    Monitor,
    Sparkles,
    Palette,
    Server,
    FolderCog,
    Check,
    X,
    Loader2,
    Save,
    MapPin,
    Globe,
    Building2,
    RefreshCw,
    Info,
    Github,
    ExternalLink,
    Heart,
    UserCog,
    FolderOpen,
    Database,
    HardDrive,
    Trash2,
    Timer,
    Type,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useSimpleToast } from "@/components/ui/simple-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
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
import { locales, localeNames, type Locale } from "@/i18n/config";
import { getUserLocaleSync, setUserLocaleSync } from "@/i18n/locale";
import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useSidebarMica } from "@/hooks/use-sidebar-mica";


const sections = [
    { id: "appearance", icon: Palette, labelKey: "appearance" as const, descKey: "generalDesc" as const },
    { id: "accountSettings", icon: UserCog, labelKey: "accountSettings" as const, descKey: "accountSettingsDesc" as const },
    { id: "antigravity", icon: Sparkles, labelKey: "antigravity" as const, descKey: "antigravityDesc" as const },
    { id: "proxy", icon: Server, labelKey: "proxy" as const, descKey: "proxyMenuDesc" as const },
    { id: "advanced", icon: FolderCog, labelKey: "advanced" as const, descKey: "dataDirDesc" as const },
    { id: "about", icon: Info, labelKey: "about" as const, descKey: "aboutDesc" as const },
];

const API_BASE = "http://127.0.0.1:8046/api";
const APP_VERSION = "v0.1.0";

function formatBytes(bytes: number, decimals = 2) {
    if (!+bytes) return "0 B";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export default function SettingsPage() {
    const t = useTranslations("settings");
    const { theme, setTheme, resolvedTheme } = useTheme();
    const [mounted, setMounted] = useState(false);
    const [activeSection, setActiveSection] = useState("appearance");
    const [proxyEnabled, setProxyEnabled] = useState(false);
    const [proxyUrl, setProxyUrl] = useState("");
    const [proxyDirty, setProxyDirty] = useState(false);
    const [proxySaving, setProxySaving] = useState(false);
    const [proxySaved, setProxySaved] = useState(false);
    const [proxyStatusLoading, setProxyStatusLoading] = useState(false);
    const [proxyStatus, setProxyStatus] = useState<{
        enabled: boolean;
        connected?: boolean;
        latency_ms?: number;
        ip?: string;
        country?: string;
        region?: string;
        city?: string;
        org?: string;
        error?: string;
        ip_error?: string;
    } | null>(null);

    const { mica, setMica } = useSidebarMica();
    const [currentLocale, setCurrentLocale] = useState<string>("");

    // Auto-refresh settings
    const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
    const [autoRefreshAntigravityEnabled, setAutoRefreshAntigravityEnabled] = useState(true);
    const [autoRefreshInterval, setAutoRefreshInterval] = useState("15");

    // Font settings
    const [fontSize, setFontSize] = useState("16");
    const [fontFamily, setFontFamily] = useState("inter");

    const [dataDir, setDataDir] = useState("");

    // Antigravity settings
    const [antigravityPath, setAntigravityPath] = useState("");
    const [antigravityArgs, setAntigravityArgs] = useState("");
    const [antigravityCacheLoading, setAntigravityCacheLoading] = useState(false);
    const [antigravityCacheConfirm, setAntigravityCacheConfirm] = useState(false);
    const [antigravityDetectStatus, setAntigravityDetectStatus] = useState<"idle" | "detecting" | "success" | "fail">("idle");
    const [antigravityArgsDetecting, setAntigravityArgsDetecting] = useState(false);

    useEffect(() => {
        const savedSize = localStorage.getItem("nullgravity_font_size");
        if (savedSize) setFontSize(savedSize);
        const savedFont = localStorage.getItem("nullgravity_font_family");
        if (savedFont) setFontFamily(savedFont);
    }, []);

    useEffect(() => {
        document.documentElement.style.fontSize = `${fontSize}px`;

        // Helper to get font value
        let fontVal = "";
        if (fontFamily === "inter") {
            // Reset to default (remove inline styles so CSS takes over)
            document.documentElement.style.removeProperty("--font-sans");
            document.body.style.removeProperty("font-family");
        } else {
            if (fontFamily === "system") {
                fontVal = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'";
            } else {
                fontVal = fontFamily;
            }
            // Set both variable and direct style to ensure it applies
            document.documentElement.style.setProperty("--font-sans", fontVal);
            document.body.style.fontFamily = fontVal;
        }
    }, [fontSize, fontFamily]);


    // Load settings from backend
    const loadSettings = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/settings/`);
            if (res.ok) {
                const data = await res.json();
                setProxyUrl(data.settings.proxy_url || "");
                setProxyEnabled(data.settings.proxy_enabled === "true");
                setAutoRefreshEnabled(data.settings.auto_refresh_enabled === "true");
                setAutoRefreshAntigravityEnabled(data.settings.auto_refresh_antigravity_enabled !== "false");
                setAutoRefreshInterval(data.settings.auto_refresh_interval || "15");
                setAntigravityPath(data.settings.antigravity_path || "");
                setAntigravityArgs(data.settings.antigravity_args || "");
                setDataDir(data.settings.data_dir || "");
            }
        } catch { }
    }, []);

    useEffect(() => {
        setMounted(true);
        setCurrentLocale(getUserLocaleSync());
        loadSettings();
    }, [loadSettings]);

    // Check proxy status
    const checkProxyStatus = useCallback(async (force: boolean = false) => {
        setProxyStatusLoading(true);
        try {
            const endpoint = force
                ? `${API_BASE}/settings/proxy/status?force=true`
                : `${API_BASE}/settings/proxy/status`;
            const res = await fetch(endpoint);
            if (res.ok) {
                setProxyStatus(await res.json());
            }
        } catch { }
        setProxyStatusLoading(false);
    }, []);

    // Initial load & refreshed on mount
    useEffect(() => {
        if (mounted) {
            checkProxyStatus(false);
        }
    }, [mounted, checkProxyStatus]);

    // Open data directory
    const openDataDir = useCallback(async () => {
        try {
            await fetch(`${API_BASE}/settings/data-dir/open`, { method: "POST" });
        } catch { }
    }, []);

    // Storage stats
    const [storageStats, setStorageStats] = useState<{
        total_size: number;
        db_size: number;
        avatars_size: number;
        logs_count: number;
        events_count: number;
    } | null>(null);

    const [clearDialogOpen, setClearDialogOpen] = useState(false);
    const { toast } = useSimpleToast();

    const loadStorageStats = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/settings/storage/stats`);
            if (res.ok) {
                setStorageStats(await res.json());
            }
        } catch { }
    }, []);

    useEffect(() => {
        if (activeSection === "advanced") {
            loadStorageStats();
        }
    }, [activeSection, loadStorageStats]);

    const confirmClearStorage = async () => {
        setClearDialogOpen(false);
        try {
            await fetch(`${API_BASE}/settings/storage/clear?type=all`, { method: "POST" });
            loadStorageStats();
            toast({
                title: t("cleared"),
                description: t("clearedDesc"),
                variant: "success",
            });
        } catch { }
    };

    // Save proxy settings (url + enabled)
    const handleSaveProxy = async (newUrl?: string, newEnabled?: boolean) => {
        const urlToSave = newUrl !== undefined ? newUrl : proxyUrl;
        const enabledToSave = newEnabled !== undefined ? newEnabled : proxyEnabled;

        setProxySaving(true);
        setProxySaved(false);
        try {
            await fetch(`${API_BASE}/settings/`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify([
                    { key: "proxy_url", value: urlToSave.trim() },
                    { key: "proxy_enabled", value: String(enabledToSave) }
                ]),
            });
            setProxyDirty(false);
            setProxySaved(true);
            setTimeout(() => setProxySaved(false), 2000);

            // Re-check status if enabled
            if (enabledToSave) {
                // small delay to let backend cache update, then force check
                setTimeout(() => checkProxyStatus(true), 100);
            } else {
                setProxyStatus(null);
            }
        } catch { }
        setProxySaving(false);
    };

    const handleToggleProxy = (checked: boolean) => {
        setProxyEnabled(checked);
        handleSaveProxy(undefined, checked);
    };

    // Save auto-refresh settings
    const handleSaveAutoRefresh = async (key: string, value: string) => {
        try {
            await fetch(`${API_BASE}/settings/`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify([{ key, value }]),
            });
        } catch { }
    };

    const handleToggleAutoRefresh = (checked: boolean) => {
        setAutoRefreshEnabled(checked);
        handleSaveAutoRefresh("auto_refresh_enabled", String(checked));
    };

    const handleToggleAutoRefreshAntigravity = (checked: boolean) => {
        setAutoRefreshAntigravityEnabled(checked);
        handleSaveAutoRefresh("auto_refresh_antigravity_enabled", String(checked));
    };

    const handleChangeInterval = (value: string) => {
        setAutoRefreshInterval(value);
        handleSaveAutoRefresh("auto_refresh_interval", value);
    };
    function handleLocaleChange(locale: string) {
        setUserLocaleSync(locale as Locale);
    }

    // Using simple helpers for local font persistence
    const handleFontFamilyChange = (value: string) => {
        setFontFamily(value);
        localStorage.setItem("nullgravity_font_family", value);
    };

    const handleFontSizeChange = (value: string) => {
        setFontSize(value);
        localStorage.setItem("nullgravity_font_size", value);
    };

    // Antigravity handlers
    const handleSaveAntigravity = async (key: string, value: string) => {
        try {
            await fetch(`${API_BASE}/settings/`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify([{ key, value }]),
            });
        } catch { }
    };

    // const { toast } = useSimpleToast(); // use top-level declaration

    const handleDetectAntigravity = async () => {
        setAntigravityDetectStatus("detecting");
        try {
            const res = await fetch(`${API_BASE}/settings/antigravity/detect`);
            if (res.ok) {
                const data = await res.json();
                if (data.path) {
                    setAntigravityPath(data.path);
                    handleSaveAntigravity("antigravity_path", data.path);
                    setAntigravityDetectStatus("success");
                    toast({
                        title: t('antigravityDetectSuccess'),
                        description: data.path,
                        variant: "success",
                    });
                    setTimeout(() => setAntigravityDetectStatus("idle"), 2000);
                } else {
                    setAntigravityDetectStatus("fail");
                    toast({
                        title: t('antigravityDetectFail'),
                        description: t('antigravityDetectFailDesc'),
                        variant: "error",
                    });
                    setTimeout(() => setAntigravityDetectStatus("idle"), 2000);
                }
            } else {
                setAntigravityDetectStatus("fail");
                toast({
                    title: t('antigravityDetectFail'),
                    description: "Unknown error",
                    variant: "error",
                });
                setTimeout(() => setAntigravityDetectStatus("idle"), 2000);
            }
        } catch {
            setAntigravityDetectStatus("fail");
            toast({
                title: t('antigravityDetectFail'),
                description: "Network error",
                variant: "error",
            });
            setTimeout(() => setAntigravityDetectStatus("idle"), 2000);
        }
    };

    const handleSelectAntigravity = async () => {
        try {
            const res = await fetch(`${API_BASE}/settings/antigravity/browse`, {
                method: "POST",
            });
            if (res.ok) {
                const data = await res.json();
                if (data.path) {
                    setAntigravityPath(data.path);
                    handleSaveAntigravity("antigravity_path", data.path);
                    toast({
                        title: t('antigravityDetectSuccess'),
                        description: data.path,
                        variant: "success",
                    });
                }
            }
        } catch {
            toast({
                title: t('antigravityDetectFail'),
                description: "Failed to open file dialog",
                variant: "error",
            });
        }
    };

    const handleDetectAntigravityArgs = async () => {
        setAntigravityArgsDetecting(true);
        try {
            const res = await fetch(`${API_BASE}/settings/antigravity/args`);
            if (res.ok) {
                const data = await res.json();
                if (data.detected && data.args) {
                    setAntigravityArgs(data.args);
                    handleSaveAntigravity("antigravity_args", data.args);
                    toast({
                        description: data.args,
                        variant: "success",
                    });
                } else if (data.process_found) {
                    // Process is running but no custom args to capture
                    toast({
                        description: t("antigravityArgsDefault"),
                        variant: "default",
                    });
                } else {
                    // No process found at all
                    toast({
                        description: t("antigravityArgsNotDetected"),
                        variant: "warning",
                    });
                }
            }
        } catch {
            toast({
                description: "Network error",
                variant: "error",
            });
        }
        setAntigravityArgsDetecting(false);
    };

    const handleClearAntigravityCache = async () => {
        if (!antigravityCacheConfirm) {
            setAntigravityCacheConfirm(true);
            setTimeout(() => setAntigravityCacheConfirm(false), 3000); // Reset after 3s
            return;
        }

        setAntigravityCacheLoading(true);
        setAntigravityCacheConfirm(false);
        try {
            await fetch(`${API_BASE}/settings/antigravity/clear-cache`, { method: "POST" });
            const timer = setTimeout(() => setAntigravityCacheLoading(false), 1000);
            return () => clearTimeout(timer);
        } catch {
            setAntigravityCacheLoading(false);
        }
    };

    const activeInfo = sections.find((s) => s.id === activeSection)!;

    return (
        /* Break out of parent's p-6 padding, fill full container height */
        <div className="-m-6 flex h-[calc(100%+48px)] overflow-hidden animate-in fade-in duration-500">
            {/* Left Nav Panel — visually separate, muted background */}
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
                                                    !proxyEnabled
                                                        ? "bg-neutral-300 dark:bg-neutral-600"
                                                        : proxyStatusLoading
                                                            ? "bg-blue-500 animate-pulse shadow-[0_0_6px_rgba(59,130,246,0.6)]"
                                                            : proxyStatus?.connected
                                                                ? "bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.4)]"
                                                                : proxyStatus?.connected === false
                                                                    ? "bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.4)]"
                                                                    : "bg-neutral-300 dark:bg-neutral-600"
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

            {/* Right Content Panel — main white/dark background */}
            <div className="flex-1 min-w-0 overflow-y-auto bg-muted/30 dark:bg-muted/20">
                <div className="px-8 py-6 w-full max-w-5xl mx-auto">
                    <h2 className="text-base font-semibold text-center">{t(activeInfo.labelKey)}</h2>
                </div>

                <div className="px-8 pb-8 space-y-6 w-full max-w-5xl mx-auto flex-1 flex flex-col">
                    {/* Appearance */}
                    {activeSection === "appearance" && (
                        <>
                            {/* Language */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("language")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("languageDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none">
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <Label className="text-[13px] font-medium">{t("language")}</Label>
                                        <Select value={currentLocale} onValueChange={handleLocaleChange}>
                                            <SelectTrigger className="w-[140px] h-8 text-xs">
                                                <SelectValue placeholder={t("language")} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {locales.map((locale) => (
                                                    <SelectItem key={locale} value={locale} className="text-xs">
                                                        {localeNames[locale]}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </section>

                            {/* Theme */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("theme")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("themeDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none">
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <Label className="text-[13px] font-medium">{t("theme")}</Label>
                                        <div className="flex gap-1">
                                            {[
                                                { value: "light", label: t("themeLight"), icon: Sun },
                                                { value: "dark", label: t("themeDark"), icon: Moon },
                                                { value: "system", label: t("themeSystem"), icon: Monitor },
                                            ].map((option) => {
                                                const Icon = option.icon;
                                                const isActive = mounted && (
                                                    option.value === "system"
                                                        ? theme === "system"
                                                        : theme !== "system" && resolvedTheme === option.value
                                                );
                                                return (
                                                    <Button
                                                        key={option.value}
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={() => setTheme(option.value)}
                                                        className={cn(
                                                            "gap-1.5 h-8 text-xs px-3 transition-colors border",
                                                            isActive
                                                                ? "bg-neutral-900 text-white border-neutral-900 hover:bg-neutral-800 hover:text-white dark:bg-white dark:text-neutral-900 dark:border-white dark:hover:bg-white/90 dark:hover:text-neutral-900"
                                                                : "hover:bg-accent hover:text-accent-foreground border-border"
                                                        )}
                                                    >
                                                        <Icon className="h-3.5 w-3.5" />
                                                        {option.label}
                                                    </Button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>
                            </section>

                            {/* Font Settings */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("font")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("fontDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none divide-y divide-border">
                                    {/* Font Family */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div className="flex items-center gap-2">
                                            <Type className="h-4 w-4 text-muted-foreground" />
                                            <Label className="text-[13px] font-medium">{t("fontFamily")}</Label>
                                        </div>
                                        <Select value={fontFamily} onValueChange={handleFontFamilyChange}>
                                            <SelectTrigger className="w-[180px] h-8 text-xs">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="inter" className="text-xs">Inter ({t("default")})</SelectItem>
                                                <SelectItem value="system" className="text-xs">System UI</SelectItem>
                                                <SelectItem value="Arial, sans-serif" className="text-xs font-[Arial]">Arial</SelectItem>
                                                <SelectItem value="'Roboto', sans-serif" className="text-xs font-[Roboto]">Roboto</SelectItem>
                                                <SelectItem value="'Times New Roman', serif" className="text-xs font-[Times]">Serif</SelectItem>
                                                <SelectItem value="monospace" className="text-xs font-mono">Monospace</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Font Size */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div className="flex items-center gap-2">
                                            <span className="h-4 w-4 flex items-center justify-center text-[10px] font-bold text-muted-foreground">AG</span>
                                            <Label className="text-[13px] font-medium">{t("fontSize")}</Label>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Select value={fontSize} onValueChange={handleFontSizeChange}>
                                                <SelectTrigger className="w-[130px] h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="12" className="text-xs">12px</SelectItem>
                                                    <SelectItem value="13" className="text-xs">13px</SelectItem>
                                                    <SelectItem value="14" className="text-xs">14px</SelectItem>
                                                    <SelectItem value="15" className="text-xs">15px</SelectItem>
                                                    <SelectItem value="16" className="text-xs">16px ({t("default")})</SelectItem>
                                                    <SelectItem value="18" className="text-xs">18px</SelectItem>
                                                    <SelectItem value="19" className="text-xs">19px</SelectItem>
                                                    <SelectItem value="20" className="text-xs">20px</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            {/* Sidebar Effect */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("sidebarEffect")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("sidebarEffectDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none">
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <Label className="text-[13px] font-medium">{t("sidebarEffect")}</Label>
                                        <div className="flex gap-1">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => setMica(false)}
                                                className={cn(
                                                    "gap-1.5 h-8 text-xs px-3 transition-colors border",
                                                    !mica
                                                        ? "bg-neutral-900 text-white border-neutral-900 hover:bg-neutral-800 hover:text-white dark:bg-white dark:text-neutral-900 dark:border-white dark:hover:bg-white/90 dark:hover:text-neutral-900"
                                                        : "hover:bg-accent hover:text-accent-foreground border-border"
                                                )}
                                            >
                                                {t("sidebarDefault")}
                                            </Button>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => setMica(true)}
                                                className={cn(
                                                    "gap-1.5 h-8 text-xs px-3 transition-colors border",
                                                    mica
                                                        ? "bg-neutral-900 text-white border-neutral-900 hover:bg-neutral-800 hover:text-white dark:bg-white dark:text-neutral-900 dark:border-white dark:hover:bg-white/90 dark:hover:text-neutral-900"
                                                        : "hover:bg-accent hover:text-accent-foreground border-border"
                                                )}
                                            >
                                                <Sparkles className="h-3.5 w-3.5" />
                                                {t("sidebarMica")}
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </>
                    )}

                    {/* Account Settings */}
                    {activeSection === "accountSettings" && (
                        <>
                            {/* Auto Refresh */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("autoRefresh")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("autoRefreshDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none divide-y divide-border">

                                    {/* Enable Switch */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("autoRefreshEnabled")}</Label>
                                            <p className="text-[11px] text-muted-foreground mt-0.5">
                                            </p>
                                        </div>
                                        <Switch
                                            checked={autoRefreshEnabled}
                                            onCheckedChange={handleToggleAutoRefresh}
                                            size="sm"
                                        />
                                    </div>

                                    {/* Antigravity Toggle */}
                                    <div className={cn("flex items-center justify-between px-4 py-3.5 transition-opacity", !autoRefreshEnabled && "opacity-50 pointer-events-none")}>
                                        <Label className="text-[13px] font-medium">{t("autoRefreshAntigravity")}</Label>
                                        <Switch
                                            checked={autoRefreshAntigravityEnabled}
                                            onCheckedChange={handleToggleAutoRefreshAntigravity}
                                            size="sm"
                                        />
                                    </div>

                                    {/* Interval */}
                                    <div className={cn("flex items-center justify-between px-4 py-3.5 transition-opacity", !autoRefreshEnabled && "opacity-50 pointer-events-none")}>
                                        <div>
                                            <Label className="text-[13px] font-medium">{t("autoRefreshInterval")}</Label>
                                            <p className="text-[11px] text-muted-foreground mt-0.5">
                                                {t("autoRefreshIntervalDesc")}
                                            </p>
                                        </div>
                                        <Select value={autoRefreshInterval} onValueChange={handleChangeInterval}>
                                            <SelectTrigger className="w-[120px] h-8 text-xs">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="5" className="text-xs">5 min</SelectItem>
                                                <SelectItem value="10" className="text-xs">10 min</SelectItem>
                                                <SelectItem value="15" className="text-xs">15 min</SelectItem>
                                                <SelectItem value="30" className="text-xs">30 min</SelectItem>
                                                <SelectItem value="60" className="text-xs">1 hr</SelectItem>
                                                <SelectItem value="120" className="text-xs">2 hr</SelectItem>
                                                <SelectItem value="240" className="text-xs">4 hr</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </section>
                        </>
                    )}

                    {/* Antigravity Settings */}
                    {activeSection === "antigravity" && (
                        <>
                            {/* Path */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("antigravityPath")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("antigravityDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 space-y-4">
                                    <div>
                                        <Label className="text-[13px] font-medium">{t("antigravityPath")}</Label>
                                        <div className="flex gap-2 mt-1.5">
                                            <Input
                                                readOnly
                                                value={antigravityPath || t("antigravityPathHOLDER")}
                                                className="flex-1 text-xs font-mono h-8 bg-muted/50 text-muted-foreground"
                                            />
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-8 text-xs min-w-[80px] gap-1.5"
                                                onClick={handleDetectAntigravity}
                                                disabled={antigravityDetectStatus === "detecting"}
                                            >
                                                <span className="relative h-3.5 w-3.5 shrink-0">
                                                    <RefreshCw
                                                        className={cn(
                                                            "absolute inset-0 h-3.5 w-3.5 transition-all duration-200",
                                                            antigravityDetectStatus === "detecting"
                                                                ? "opacity-0 scale-75"
                                                                : "opacity-100 scale-100"
                                                        )}
                                                    />
                                                    <Loader2
                                                        className={cn(
                                                            "absolute inset-0 h-3.5 w-3.5 animate-spin transition-all duration-200",
                                                            antigravityDetectStatus === "detecting"
                                                                ? "opacity-100 scale-100"
                                                                : "opacity-0 scale-75"
                                                        )}
                                                    />
                                                </span>
                                                {antigravityDetectStatus === "detecting"
                                                    ? t("antigravityDetecting")
                                                    : t("antigravityDetect")
                                                }
                                            </Button>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-8 text-xs gap-1.5"
                                                onClick={handleSelectAntigravity}
                                            >
                                                <FolderCog className="h-3.5 w-3.5" />
                                                {t("antigravitySelect")}
                                            </Button>
                                        </div>
                                        <p className="text-[11px] text-muted-foreground mt-1.5">
                                            {t("antigravityPathDesc")}
                                        </p>
                                    </div>
                                </div>
                            </section>

                            {/* Launch Args */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("antigravityArgs")}</h3>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 space-y-4">
                                    <div>
                                        <Label className="text-[13px] font-medium">{t("antigravityArgs")}</Label>
                                        <div className="flex gap-2 mt-1.5">
                                            <Input
                                                value={antigravityArgs}
                                                onChange={(e) => setAntigravityArgs(e.target.value)}
                                                onBlur={(e) => handleSaveAntigravity("antigravity_args", e.target.value)}
                                                placeholder={t("antigravityArgsPlaceholder")}
                                                className="flex-1 text-xs font-mono h-8"
                                            />
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-8 text-xs"
                                                onClick={handleDetectAntigravityArgs}
                                                disabled={antigravityArgsDetecting}
                                            >
                                                {antigravityArgsDetecting
                                                    ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                                    : <RefreshCw className="mr-1 h-3 w-3" />}
                                                {t("antigravityDetect")}
                                            </Button>
                                        </div>
                                        <p className="text-[11px] text-muted-foreground mt-1.5">
                                            {t("antigravityArgsDesc")}
                                        </p>
                                    </div>
                                </div>
                            </section>

                            {/* Cache */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("antigravityCache")}</h3>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4">
                                    <p className="text-xs text-muted-foreground mb-4 whitespace-pre-wrap">
                                        {t("antigravityCacheDesc")}
                                    </p>
                                    <Button
                                        variant={antigravityCacheConfirm ? "default" : "destructive"}
                                        size="sm"
                                        className="h-8 text-xs transition-all duration-300"
                                        onClick={handleClearAntigravityCache}
                                        disabled={antigravityCacheLoading}
                                    >
                                        {antigravityCacheLoading && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
                                        {antigravityCacheConfirm ? t("antigravityCacheConfirm") : t("antigravityCacheBtn")}
                                    </Button>
                                </div>
                            </section>
                        </>
                    )}

                    {/* Proxy */}
                    {activeSection === "proxy" && (
                        <>
                            {/* Upstream Proxy */}
                            <section>
                                <div className="mb-2">
                                    <h3 className="text-sm font-semibold">{t("proxyUpstream")}</h3>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {t("proxyUpstreamDesc")}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none divide-y divide-border">

                                    {/* Enable Switch */}
                                    <div className="flex items-center justify-between px-4 py-3.5">
                                        <Label className="text-[13px] font-medium">{t("proxyEnabled")}</Label>
                                        <Switch
                                            checked={proxyEnabled}
                                            onCheckedChange={handleToggleProxy}
                                            size="sm"
                                        />
                                    </div>

                                    {/* Proxy URL */}
                                    <div className={cn("px-4 py-3.5 space-y-2 transition-opacity", !proxyEnabled && "opacity-50 pointer-events-none")}>
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <Label className="text-[13px] font-medium">{t("proxyUrl")}</Label>
                                                <p className="text-xs text-muted-foreground mt-0.5">
                                                    {t("proxyUrlDesc")}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Input
                                                value={proxyUrl}
                                                onChange={(e) => {
                                                    setProxyUrl(e.target.value);
                                                    setProxyDirty(true);
                                                }}
                                                placeholder="http://127.0.0.1:7890"
                                                className="flex-1 h-8 text-xs font-mono"
                                            />
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleSaveProxy()}
                                                disabled={proxySaving || !proxyDirty}
                                                className="h-8 text-xs px-3 gap-1.5"
                                            >
                                                {proxySaving ? (
                                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                ) : proxySaved ? (
                                                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                                                ) : (
                                                    <Save className="h-3.5 w-3.5" />
                                                )}
                                                {proxySaved ? t("saved") : t("save")}
                                            </Button>
                                        </div>
                                        <p className="text-[11px] text-muted-foreground">
                                            {t("proxyExamples")}
                                        </p>
                                    </div>

                                    {/* Proxy Status */}
                                    <div className="px-4 py-3.5">
                                        <div className="mb-2 flex items-center gap-2">
                                            <Label className="text-[13px] font-medium">{t("proxyStatus")}</Label>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-5 w-5 text-muted-foreground hover:text-foreground"
                                                onClick={() => checkProxyStatus(true)}
                                                disabled={!proxyEnabled || proxyStatusLoading}
                                                title={t("proxyStatusRefresh")}
                                            >
                                                <RefreshCw className={cn("h-3 w-3", proxyStatusLoading && "animate-spin")} />
                                            </Button>
                                        </div>

                                        {!proxyEnabled ? (
                                            <div className="flex items-center gap-2 text-muted-foreground text-xs px-1">
                                                <div className="h-2 w-2 rounded-full bg-neutral-300 dark:bg-neutral-600" />
                                                {t("proxyStatusDisabled")}
                                            </div>
                                        ) : proxyStatusLoading ? (
                                            <div className="flex items-center gap-2 text-muted-foreground text-xs px-1">
                                                <Loader2 className="h-3 w-3 animate-spin" />
                                                {t("proxyStatusChecking")}
                                            </div>
                                        ) : proxyStatus && proxyStatus.enabled ? (
                                            <div className="space-y-2.5">
                                                {/* Connection Status */}
                                                {proxyStatus.connected ? (
                                                    <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-xs px-1 font-medium">
                                                        <div className="h-2 w-2 rounded-full bg-emerald-500" />
                                                        {t("proxyStatusOk")} — {proxyStatus.latency_ms}ms
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-xs px-1">
                                                        <div className="h-2 w-2 rounded-full bg-red-500" />
                                                        {t("proxyStatusFail")}
                                                        {proxyStatus.error && <span className="text-muted-foreground">- {proxyStatus.error}</span>}
                                                    </div>
                                                )}

                                                {/* IP Info Card (only shown when connected) */}
                                                {proxyStatus.connected && proxyStatus.ip && (
                                                    <div className="bg-muted/40 rounded-md p-3 text-xs space-y-1.5 border border-border/50">
                                                        <div className="flex items-center gap-2">
                                                            <Server className="h-3 w-3 text-muted-foreground" />
                                                            <span className="text-muted-foreground">{t("proxyIp")}:</span>
                                                            <span className="font-mono">{proxyStatus.ip}</span>
                                                        </div>
                                                        {(proxyStatus.city || proxyStatus.country) && (
                                                            <div className="flex items-center gap-2">
                                                                <MapPin className="h-3 w-3 text-muted-foreground" />
                                                                <span className="text-muted-foreground">{t("proxyLocation")}:</span>
                                                                <span>
                                                                    {[proxyStatus.city, proxyStatus.region, proxyStatus.country].filter(Boolean).join(", ")}
                                                                </span>
                                                            </div>
                                                        )}
                                                        {proxyStatus.org && (
                                                            <div className="flex items-center gap-2">
                                                                <Building2 className="h-3 w-3 text-muted-foreground" />
                                                                <span className="text-muted-foreground">{t("proxyOrg")}:</span>
                                                                <span className="truncate max-w-[200px]">{proxyStatus.org}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

                                                {/* IP lookup failed but proxy works */}
                                                {proxyStatus.connected && !proxyStatus.ip && proxyStatus.ip_error && (
                                                    <div className="bg-amber-500/5 rounded-md px-3 py-2 text-xs text-amber-600 dark:text-amber-400 border border-amber-500/20">
                                                        {t("proxyIpLookupFailed")}
                                                    </div>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="flex items-center gap-2 text-muted-foreground text-xs px-1">
                                                <div className="h-2 w-2 rounded-full bg-neutral-300 dark:bg-neutral-600" />
                                                {t("proxyStatusUnknown")}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </section>
                        </>

                    )}

                    {/* Advanced */}
                    {activeSection === "advanced" && (
                        <section>
                            <div className="mb-2">
                                <h3 className="text-sm font-semibold">{t("advanced")}</h3>
                                <p className="text-xs text-muted-foreground mt-0.5">
                                    {t("dataDirDesc")}
                                </p>
                            </div>
                            <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4">
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-[13px] font-medium">{t("dataDir")}</Label>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-7 text-xs gap-1.5"
                                            onClick={openDataDir}
                                        >
                                            <FolderOpen className="h-3.5 w-3.5" />
                                            {t("openFolder")}
                                        </Button>
                                    </div>
                                    <Input
                                        readOnly
                                        value={dataDir}
                                        className="font-mono text-xs w-full bg-muted/30"
                                        title={dataDir}
                                    />
                                    <p className="text-xs text-muted-foreground leading-relaxed">
                                        {t("dataDirLongDesc")}
                                    </p>
                                </div>
                            </div>

                            {/* Storage Usage */}
                            <div className="mt-4">
                                <h4 className="text-xs font-semibold mb-3 px-1">{t("storageUsage")}</h4>
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        {/* Core Data */}
                                        <div className="bg-muted/30 p-3 rounded-md border border-border/50 h-full flex flex-col">
                                            <div className="flex items-center gap-2 mb-2 text-muted-foreground h-6">
                                                <Database className="h-3.5 w-3.5" />
                                                <span className="text-xs font-medium">{t("coreData")}</span>
                                            </div>
                                            <div className="text-xl font-bold tracking-tight mb-1">
                                                {storageStats ? formatBytes(storageStats.db_size) : "..."}
                                            </div>
                                            <div className="text-[10px] text-muted-foreground leading-tight mt-auto">
                                                {t("coreDataDesc")}
                                            </div>
                                        </div>

                                        {/* Cache Data */}
                                        <div className="bg-muted/30 p-3 rounded-md border border-border/50 h-full flex flex-col">
                                            <div className="flex items-center justify-between mb-2 text-muted-foreground h-6">
                                                <div className="flex items-center gap-2">
                                                    <HardDrive className="h-3.5 w-3.5" />
                                                    <span className="text-xs font-medium">{t("cacheData")}</span>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 -mr-1 text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 dark:hover:text-red-400 rounded-full transition-colors"
                                                    onClick={() => setClearDialogOpen(true)}
                                                    title={t("clearCache")}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            </div>
                                            <div className="text-xl font-bold tracking-tight mb-1">
                                                {storageStats ? formatBytes(storageStats.avatars_size) : "..."}
                                            </div>
                                            <div className="text-[10px] text-muted-foreground leading-tight mt-auto">
                                                {storageStats ? t("logsCount", { count: storageStats.logs_count + storageStats.events_count }) : "..."}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Clear Dialog */}
                            <Dialog open={clearDialogOpen} onOpenChange={setClearDialogOpen}>
                                <DialogContent className="sm:max-w-[425px]">
                                    <DialogHeader>
                                        <DialogTitle>{t("clearCache")}</DialogTitle>
                                        <DialogDescription className="pt-2">
                                            {t("clearCacheConfirm")}
                                        </DialogDescription>
                                    </DialogHeader>
                                    <DialogFooter>
                                        <Button variant="outline" onClick={() => setClearDialogOpen(false)}>
                                            {t("cancel")}
                                        </Button>
                                        <Button variant="destructive" onClick={confirmClearStorage}>
                                            {t("confirm")}
                                        </Button>
                                    </DialogFooter>
                                </DialogContent>
                            </Dialog>
                        </section>
                    )}

                    {/* About */}
                    {activeSection === "about" && (
                        <section className="flex flex-col items-center justify-center pt-8 pb-4 text-center animate-in fade-in slide-in-from-bottom-2 duration-500">
                            {/* Avatar with glow */}
                            <div className="relative mb-6 group">
                                <div className="absolute -inset-1 rounded-full bg-gradient-to-tr from-violet-500/40 via-fuchsia-500/40 to-orange-500/40 blur-md opacity-70 group-hover:opacity-100 transition duration-500" />
                                <div className="relative h-24 w-24 overflow-hidden rounded-full border-2 border-background shadow-xl">
                                    <Image
                                        src="/logo.svg"
                                        alt="NullGravity Logo"
                                        fill
                                        className="object-cover transition-transform duration-700 group-hover:scale-110"
                                    />
                                </div>
                            </div>

                            {/* App Info */}
                            <h3 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-neutral-900 via-neutral-600 to-neutral-900 dark:from-white dark:via-neutral-200 dark:to-white mb-2">
                                NullGravity
                            </h3>
                            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-muted/50 text-xs font-medium text-muted-foreground mb-6 border border-border/50">
                                <span>{APP_VERSION}</span>
                            </div>

                            {/* Author Info */}
                            <div className="w-full max-w-sm space-y-4">
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 text-left">
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">{t("author")}</h4>
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 relative overflow-hidden rounded-full bg-muted shrink-0 shadow-sm border border-border/10">
                                            <Image src="/author.jpg" alt="Cyerol" fill className="object-cover" />
                                        </div>
                                        <div>
                                            <div className="font-medium text-sm">Cyerol</div>
                                            <div className="text-xs text-muted-foreground">Vibe Coding Developer</div>
                                        </div>
                                    </div>
                                </div>

                                {/* GitHub Repo */}
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 text-left">
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">{t("repository")}</h4>
                                    <a
                                        href="https://github.com/Tonwed/NullGravity"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center group -mx-2 px-2 py-2 rounded-lg hover:bg-muted/50 transition-colors"
                                    >
                                        <div className="flex items-center gap-3 flex-1">
                                            <div className="h-10 w-10 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center shrink-0 border border-border/50 group-hover:border-border transition-colors">
                                                <Github className="h-5 w-5 text-neutral-700 dark:text-neutral-300" />
                                            </div>
                                            <div>
                                                <div className="font-medium text-sm flex items-center gap-1.5">
                                                    Tonwed/NullGravity
                                                    <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                                                </div>
                                                <div className="text-xs text-muted-foreground">GitHub</div>
                                            </div>
                                        </div>
                                    </a>
                                </div>

                                {/* Sponsor */}
                                <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-4 text-left">
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">{t("sponsor")}</h4>
                                    <a
                                        href="https://github.com/sponsors/Tonwed" // Assuming this or general link
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center group -mx-2 px-2 py-2 rounded-lg hover:bg-muted/50 transition-colors"
                                    >
                                        <div className="flex items-center gap-3 flex-1">
                                            <div className="h-10 w-10 rounded-full bg-pink-100 dark:bg-pink-900/20 flex items-center justify-center shrink-0 border border-border/50 group-hover:border-border transition-colors">
                                                <Heart className="h-5 w-5 text-pink-600 dark:text-pink-400 group-hover:scale-110 transition-transform" />
                                            </div>
                                            <div>
                                                <div className="font-medium text-sm flex items-center gap-1.5">
                                                    {t("openSponsor")}
                                                    <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                                                </div>
                                                <div className="text-xs text-muted-foreground">GitHub Sponsors</div>
                                            </div>
                                        </div>
                                    </a>
                                </div>
                            </div>
                        </section>
                    )}
                </div>
            </div>
        </div>
    );
}
