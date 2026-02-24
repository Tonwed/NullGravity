"use client";

import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
    LayoutDashboard,
    Users,
    Settings,
    ChevronLeft,
    ChevronRight,
    Orbit,
    FileText,
    Network,
} from "lucide-react";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { useState, useEffect } from "react";

const navItems = [
    { href: "/", icon: LayoutDashboard, labelKey: "dashboard" as const },
    { href: "/accounts", icon: Users, labelKey: "accounts" as const },
    { href: "/api-proxy", icon: Network, labelKey: "apiProxy" as const },
    { href: "/logs", icon: FileText, labelKey: "logs" as const },
    { href: "/settings", icon: Settings, labelKey: "settings" as const },
];

const SIDEBAR_EXPANDED = 220;
const SIDEBAR_COLLAPSED = 60;
const ICON_AREA = 60; // fixed icon column width

export function AppSidebar() {
    const t = useTranslations("nav");
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);
    const [accountCount, setAccountCount] = useState<number | null>(null);

    useEffect(() => {
        const fetchCount = () => {
            fetch("http://127.0.0.1:8046/api/accounts/?page=1&page_size=1")
                .then(r => r.json())
                .then(data => {
                    if (typeof data.total === "number") setAccountCount(data.total);
                })
                .catch(() => { /* ignore */ });
        };
        fetchCount();
        const interval = setInterval(fetchCount, 30000);
        return () => clearInterval(interval);
    }, []);

    return (
        <aside
            className="sidebar-mica-bg flex flex-col text-sidebar-foreground transition-[width] duration-200 ease-in-out overflow-hidden shrink-0 select-none"
            style={{ width: collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED }}
        >
            {/* Logo - icon always centered in ICON_AREA */}
            <div className="flex h-14 items-center shrink-0">
                <div
                    className="flex items-center justify-center shrink-0"
                    style={{ width: ICON_AREA }}
                >
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-foreground/8">
                        <Orbit className="h-4 w-4 text-foreground/70" />
                    </div>
                </div>
                <span className="text-sm font-semibold tracking-tight text-foreground whitespace-nowrap opacity-100 transition-opacity duration-150"
                    style={{ opacity: collapsed ? 0 : 1 }}
                >
                    NullGravity
                </span>
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-0.5 px-2 pt-1">
                {navItems.map((item) => {
                    const isActive =
                        item.href === "/"
                            ? pathname === "/"
                            : pathname.startsWith(item.href);

                    const linkContent = (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "group flex items-center rounded-md h-8 text-[13px] font-medium transition-colors whitespace-nowrap",
                                isActive
                                    ? "bg-neutral-200 text-foreground dark:bg-white/20 dark:text-white"
                                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
                            )}
                        >
                            {/* Icon always centered in fixed width area */}
                            <div
                                className="flex items-center justify-center shrink-0"
                                style={{ width: ICON_AREA - 16 }} /* 60 - 16 (px-2 padding) = 44 */
                            >
                                <item.icon className="h-4 w-4 shrink-0" />
                            </div>
                            <span
                                className="inline-flex items-center gap-1 transition-opacity duration-150"
                                style={{ opacity: collapsed ? 0 : 1 }}
                            >
                                {t(item.labelKey)}
                                {item.labelKey === "accounts" && accountCount !== null && (
                                    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-foreground/10 dark:bg-white/20 px-1 text-[12px] leading-none font-semibold text-muted-foreground dark:text-white/70 tabular-nums">
                                        {accountCount}
                                    </span>
                                )}
                            </span>
                        </Link>
                    );

                    if (collapsed) {
                        return (
                            <Tooltip key={item.href} delayDuration={0}>
                                <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
                                <TooltipContent side="right" className="text-xs">
                                    {t(item.labelKey)}
                                    {item.labelKey === "accounts" && accountCount !== null && (
                                        <span className="ml-1 text-muted-foreground">({accountCount})</span>
                                    )}
                                </TooltipContent>
                            </Tooltip>
                        );
                    }

                    return <div key={item.href}>{linkContent}</div>;
                })}
            </nav>

            {/* Collapse Toggle */}
            <div className="pb-3 px-2">
                <Tooltip delayDuration={0}>
                    <TooltipTrigger asChild>
                        <button
                            onClick={() => setCollapsed(!collapsed)}
                            className="flex items-center w-full h-8 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60 transition-colors"
                        >
                            <div
                                className="flex items-center justify-center shrink-0"
                                style={{ width: ICON_AREA - 16 }}
                            >
                                {collapsed ? (
                                    <ChevronRight className="h-4 w-4" />
                                ) : (
                                    <ChevronLeft className="h-4 w-4" />
                                )}
                            </div>
                            <span
                                className="text-[13px] font-medium whitespace-nowrap transition-opacity duration-150"
                                style={{ opacity: collapsed ? 0 : 1 }}
                            >
                                {t("collapse")}
                            </span>
                        </button>
                    </TooltipTrigger>
                    {collapsed && (
                        <TooltipContent side="right" className="text-xs">
                            {t("collapse")}
                        </TooltipContent>
                    )}
                </Tooltip>
            </div>
        </aside>
    );
}
