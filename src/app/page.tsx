"use client";

import { useTranslations } from "next-intl";
import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Info,
  Loader2,
  MoreHorizontal,
  Play,
  Power,
  RefreshCw,
  Server,
  TrendingUp,
  UserMinus,
  UserPlus,
  Users,
  Zap
} from "lucide-react";

function getEventIcon(type: string) {
  switch (type) {
    case "account.create": return UserPlus;
    case "account.delete": return UserMinus;
    case "account.validation_required": return AlertTriangle;
    case "app.launch": return Zap;
    case "system.start": return Power;
    case "proxy.change": return Server;
    case "account.update": return RefreshCw;
    case "account.sync": return RefreshCw;
    default: return Info;
  }
}

function getEventColor(level: string) {
  // Unified gray style for all events (semantic tokens adapt to dark mode)
  // Dark mode: using text-foreground/80 for higher contrast (whiter) as requested
  return "text-muted-foreground dark:text-foreground/80 bg-muted/50 border-border/60";
}
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

// --- Types ---

interface ModelQuota {
  name: string;
  remainingFraction?: number;
  resetTime?: string;
  _client_type?: string;
}

interface AccountSummary {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  avatar_cached: boolean;
  provider: string;
  status: string;
  tier?: string;
  is_forbidden: boolean;
  status_reason?: string;
  gemini_models?: ModelQuota[];
  antigravity_models?: ModelQuota[];
  last_sync_at?: string;
  has_gemini: boolean;
  has_antigravity: boolean;
}

interface EventItem {
  id: number;
  type: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string | null;
  account_email: string | null;
  account_avatar: string | null;
}

interface DashboardStats {
  total_accounts: number;
  active_accounts: number;
  forbidden_accounts: number;
  validation_required_accounts: number;
  total_requests: number;
  requests_today: number;
  success_rate?: number;
  avg_latency_ms?: number;
  proxy_enabled: boolean;
  proxy_connected?: boolean;
  proxy_ip?: string;
  proxy_latency_ms?: number;
  auto_refresh_enabled: boolean;
  backend_uptime_seconds?: number;
  accounts: AccountSummary[];
  recent_events: EventItem[];
}

const API_BASE = "http://127.0.0.1:8046/api";

// --- Components ---

function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  className,
}: {
  title: string;
  value: string | number | React.ReactNode;
  icon: React.ElementType;
  trend?: string;
  className?: string;
}) {
  return (
    <div className={cn(
      "rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none px-4 py-3 transition-colors hover:bg-accent/5",
      className
    )}>
      <div className="flex items-center justify-between space-y-0 mb-1">
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide opacity-80">{title}</p>
        <Icon className="h-3.5 w-3.5 text-muted-foreground opacity-50" />
      </div>
      <div className="flex items-baseline justify-between pt-0.5">
        <div className="text-xl font-bold tracking-tight leading-none">{value}</div>
        {trend && <p className="text-[10px] text-muted-foreground font-medium opacity-70">{trend}</p>}
      </div>
    </div>
  );
}

function QuotaProgressBar({ fraction, label, subLabel }: { fraction: number, label: string, subLabel?: string }) {
  let colorClass = "bg-primary";
  if (fraction < 0.2) colorClass = "bg-red-500";
  else if (fraction < 0.5) colorClass = "bg-yellow-500";
  else colorClass = "bg-emerald-500";

  const percentage = Math.max(0, Math.min(100, fraction * 100));

  return (
    <div className="space-y-1.5 w-full">
      <div className="flex justify-between items-center text-xs">
        <span className="font-medium truncate max-w-[120px]" title={label}>{label}</span>
        <span className="text-muted-foreground shrink-0 tabular-nums">
          {subLabel || `${percentage.toFixed(0)}%`}
        </span>
      </div>
      <div className="h-1.5 w-full bg-secondary/50 rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all duration-500 ease-out", colorClass)}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function AccountItem({ account, t }: { account: AccountSummary, t: any }) {
  const models = [...(account.gemini_models || []), ...(account.antigravity_models || [])];
  const uniqueModels = Array.from(new Map(models.map(m => [m.name, m])).values());
  const displayModels = uniqueModels.slice(0, 3);

  const getResetText = (isoTime?: string) => {
    if (!isoTime) return "";
    const date = new Date(isoTime);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();

    if (diffMs <= 0) return t("dashboard.resetsAt") + ": " + t("common.now");

    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    return `${hours}h ${minutes}m`;
  };

  return (
    <div className="flex flex-col space-y-3 p-4 border rounded-xl bg-card/50 hover:bg-accent/5 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 overflow-hidden">
          <Avatar className="h-8 w-8 border border-border/50">
            <AvatarImage
              src={account.avatar_cached ? `${API_BASE}/accounts/${account.id}/avatar` : account.avatar_url}
              className="object-cover"
            />
            <AvatarFallback className="text-[10px]">
              {account.email.substring(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm truncate" title={account.email}>{account.display_name || account.email}</span>
              {account.status_reason === "VALIDATION_REQUIRED" && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
                    </TooltipTrigger>
                    <TooltipContent>{t("dashboard.validationRequired")}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              {account.is_forbidden && (
                <Badge variant="destructive" className="h-4 px-1 text-[10px] rounded-[4px]">{t("dashboard.forbidden")}</Badge>
              )}
            </div>
            <span className="text-[11px] text-muted-foreground truncate opacity-80">{account.email}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {account.has_gemini && <Badge variant="outline" className="text-[9px] h-4 px-1 text-muted-foreground opacity-70">CLI</Badge>}
          {account.has_antigravity && <Badge variant="outline" className="text-[9px] h-4 px-1 text-muted-foreground opacity-70">AG</Badge>}
        </div>
      </div>

      {/* Quota Bars */}
      <div className="space-y-3 pt-1">
        {displayModels.length > 0 ? (
          displayModels.map((model, idx) => (
            <QuotaProgressBar
              key={`${model.name}-${idx}`}
              fraction={model.remainingFraction ?? 0}
              label={model.name.replace("models/", "")}
              subLabel={model.resetTime ? getResetText(model.resetTime) : undefined}
            />
          ))
        ) : (
          <div className="text-[10px] text-muted-foreground italic py-1 text-center opacity-70">
            {t("common.noData")}
          </div>
        )}
      </div>
    </div>
  );
}

function UptimeDisplay({ seconds, t }: { seconds: number, t: any }) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  return (
    <span className="tabular-nums font-mono text-sm tracking-tight text-foreground/90">
      {days > 0 && <span>{days}<span className="text-muted-foreground font-sans text-xs ml-0.5 mr-1.5">{t("dashboard.days")}</span></span>}
      {hours > 0 && <span>{hours}<span className="text-muted-foreground font-sans text-xs ml-0.5 mr-1.5">{t("dashboard.hours")}</span></span>}
      <span>{minutes}<span className="text-muted-foreground font-sans text-xs ml-0.5">{t("dashboard.minutes")}</span></span>
    </span>
  );
}

export default function DashboardPage() {
  const t = useTranslations();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      if (!stats) setLoading(true);
      const res = await fetch(`${API_BASE}/dashboard/stats`);
      if (!res.ok) throw new Error("Failed to fetch stats");
      const data = await res.json();
      setStats(data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t, stats]);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !stats) {
    return (
      <div className="h-full w-full flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <RefreshCw className="h-8 w-8 animate-spin opacity-50" />
          <p className="text-sm">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="h-full w-full flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4 text-destructive">
          <AlertTriangle className="h-10 w-10" />
          <p>{t("dashboard.subtitle")}</p>
          <Button onClick={fetchStats} variant="outline" size="sm">{t("common.retry")}</Button>
        </div>
      </div>
    );
  }

  const s = stats!;

  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-in fade-in duration-500">

      {/* Header - Matches Accounts Page Style */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("dashboard.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("dashboard.subtitle")}
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button onClick={fetchStats} variant="ghost" size="sm" className="h-8 w-8 p-0">
            <RefreshCw className={cn("h-4 w-4 text-muted-foreground", loading && "animate-spin")} />
          </Button>
          <Button asChild size="sm" className="h-8 gap-1.5 text-xs">
            <Link href="/accounts">
              <Users className="h-3.5 w-3.5" />
              {t("dashboard.viewAccounts")}
            </Link>
          </Button>
        </div>
      </div>

      {/* Top Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title={t("dashboard.totalAccounts")}
          value={s.total_accounts}
          icon={Users}
          trend={`${s.active_accounts} ${t("accounts.active")}`}
        />
        <StatCard
          title={t("dashboard.uptime")}
          value={<UptimeDisplay seconds={s.backend_uptime_seconds || 0} t={t} />}
          icon={Clock}
          className="bg-card"
        />
        <StatCard
          title={t("dashboard.requestsToday")}
          value={s.requests_today}
          icon={Zap}
          trend={s.total_requests > 0 ? `${t("dashboard.totalRequests")}: ${s.total_requests}` : undefined}
        />
        <StatCard
          title={t("dashboard.successRate")}
          value={s.success_rate !== null ? `${s.success_rate}%` : "--%"}
          icon={Activity}
          trend={s.avg_latency_ms ? `${s.avg_latency_ms}ms avg` : undefined}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">

        {/* Left Column: Accounts Quota */}
        <div className="lg:col-span-4 space-y-4">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              {t("dashboard.quotaOverview")}
            </h3>
            <Badge variant="outline" className="font-mono text-[10px] text-muted-foreground font-normal">
              {s.active_accounts} Active
            </Badge>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {s.accounts.length > 0 ? (
              s.accounts.map(acc => (
                <AccountItem key={acc.id} account={acc} t={t} />
              ))
            ) : (
              <div className="col-span-2 flex flex-col items-center justify-center py-10 text-center text-muted-foreground border border-dashed rounded-xl bg-card/50">
                <Users className="h-8 w-8 mb-3 opacity-20" />
                <p className="text-sm">{t("dashboard.noAccounts")}</p>
                <Button variant="link" asChild className="h-auto p-0 mt-1 text-xs">
                  <Link href="/accounts">{t("dashboard.addAccount")}</Link>
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: System & Recent Activity */}
        <div className="lg:col-span-3 space-y-4">

          {/* System Status */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium flex items-center gap-2 px-1">
              <Server className="h-4 w-4 text-muted-foreground" />
              {t("dashboard.system")}
            </h3>
            <div className="grid gap-3">
              {/* Proxy Item */}
              <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none px-4 py-3 flex items-center justify-between transition-colors hover:bg-accent/5">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "flex items-center justify-center w-8 h-8 rounded-full border",
                    s.proxy_enabled
                      ? (s.proxy_connected ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400" : "bg-red-500/10 border-red-500/20 text-red-600 dark:text-red-400")
                      : "bg-muted/50 border-border/50 text-muted-foreground"
                  )}>
                    <Server className="h-4 w-4" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[13px] font-medium leading-none">{t("dashboard.proxy")}</span>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {s.proxy_enabled ? (s.proxy_ip || t("dashboard.connected")) : t("dashboard.disabled")}
                    </span>
                  </div>
                </div>
                {s.proxy_latency_ms && (
                  <Badge variant="secondary" className="font-mono text-[10px] h-5 px-1.5 font-normal">
                    {s.proxy_latency_ms}ms
                  </Badge>
                )}
              </div>

              {/* Auto Refresh Item */}
              <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none px-4 py-3 flex items-center justify-between transition-colors hover:bg-accent/5">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "flex items-center justify-center w-8 h-8 rounded-full border",
                    s.auto_refresh_enabled
                      ? "bg-blue-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400"
                      : "bg-muted/50 border-border/50 text-muted-foreground"
                  )}>
                    <RefreshCw className="h-4 w-4" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[13px] font-medium leading-none">{t("dashboard.autoRefresh")}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {s.auto_refresh_enabled ? t("dashboard.enabled") : t("dashboard.disabled")}
                    </span>
                  </div>
                </div>
                <div className={cn("h-2 w-2 rounded-full", s.auto_refresh_enabled ? "bg-blue-500" : "bg-muted-foreground/30")} />
              </div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="space-y-3 flex-1">
            <div className="flex items-center justify-between px-1">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                {t("dashboard.recentActivity")}
              </h3>
              <Link href="/logs" className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1">
                {t("dashboard.viewLogs")} <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            <div className="space-y-3">
              {s.recent_events && s.recent_events.length > 0 ? (
                s.recent_events.slice(0, 8).map((evt) => {
                  const Icon = getEventIcon(evt.type);
                  const colorClass = getEventColor(evt.level);

                  const getEventMessage = (evt: any) => {
                    if (evt.type === "system.start") return t("events.system.start");
                    if (evt.type === "proxy.change") {
                      if (evt.message.includes("disconnected")) return t("events.proxy.disconnected");
                      const match = evt.message.match(/\((.*?)\)/);
                      return t("events.proxy.connected", { ip: match ? match[1] : (evt.details?.ip || "?") });
                    }
                    if (evt.type === "account.create") return t("events.account.create", { email: evt.account_email || "?" });
                    if (evt.type === "account.delete") return t("events.account.delete", { email: evt.account_email || "?" });
                    if (evt.type === "account.sync") return t("events.account.sync");
                    if (evt.type === "app.launch") return t("events.app.launch");
                    return evt.message;
                  };

                  const description = getEventMessage(evt);

                  return (
                    <div
                      key={evt.id}
                      className="group flex flex-col gap-2 rounded-lg border border-border/60 bg-card p-3 shadow-[0_2px_4px_-2px_rgba(0,0,0,0.05)] transition-all hover:bg-accent/5 hover:shadow-sm"
                    >
                      <div className={cn("flex gap-3", evt.account_email ? "items-start" : "items-center")}>
                        <div className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
                          colorClass,
                          evt.account_email ? "mt-0.5" : ""
                        )}>
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="flex flex-1 flex-col min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[13px] font-medium leading-tight text-foreground/90 line-clamp-2">
                              {description}
                            </span>
                            {!evt.account_email && (
                              <div className="flex items-center gap-2 whitespace-nowrap">
                                <span className="text-[10px] text-muted-foreground/50 font-mono uppercase tracking-wider">{evt.type}</span>
                                <span className="text-[10px] text-muted-foreground/70 font-mono">
                                  {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""}
                                </span>
                              </div>
                            )}
                            {evt.account_email && (
                              <span className="whitespace-nowrap text-[10px] text-muted-foreground/70 font-mono mt-0.5">
                                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""}
                              </span>
                            )}
                          </div>

                          {evt.account_email && (
                            <div className="flex items-center gap-2 mt-0.5">
                              <div className="flex items-center gap-1.5 max-w-[180px]">
                                <Avatar className="h-3.5 w-3.5 border border-border/50">
                                  <AvatarImage src={`http://127.0.0.1:8046${evt.account_avatar || ""}`} />
                                  <AvatarFallback className="text-[8px] bg-muted text-muted-foreground">?</AvatarFallback>
                                </Avatar>
                                <span className="truncate text-[11px] text-muted-foreground">{evt.account_email}</span>
                              </div>
                              <span className="text-[10px] text-muted-foreground/50 ml-auto font-mono uppercase tracking-wider">{evt.type}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="flex h-32 flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-center">
                  <Activity className="h-8 w-8 text-muted-foreground/20" />
                  <p className="text-sm text-muted-foreground/50">{t("dashboard.noActivity")}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
