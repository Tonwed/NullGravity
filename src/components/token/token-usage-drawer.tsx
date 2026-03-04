"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { X, TrendingUp, Activity, Clock, BarChart3 } from "lucide-react";
import { Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChartContainer } from "@/components/ui/chart";
import { apiFetch, getApiBase } from "@/lib/api";

const COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
];

interface TokenUsageData {
  token_id: string;
  token_name: string;
  total_requests: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_model: Array<{
    model: string;
    requests: number;
    tokens: number;
  }>;
  time_series: Array<{
    time: string;
    requests: number;
    tokens: number;
  }>;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || !payload.length) return null;

  const formatValue = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
    return value.toLocaleString();
  };

  return (
    <div className="rounded-lg border bg-background p-2 shadow-sm">
      <div className="text-xs font-medium mb-1">{label}</div>
      {payload.map((entry: any, index: number) => (
        <div key={index} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.stroke }} />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">{formatValue(entry.value)}</span>
        </div>
      ))}
    </div>
  );
};

export function TokenUsageDrawer({
  open,
  onOpenChange,
  tokenId,
  tokenName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tokenId: string | null;
  tokenName: string;
}) {
  const [data, setData] = useState<TokenUsageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("24h");
  const t = useTranslations("dashboard");

  useEffect(() => {
    if (open && tokenId) {
      fetchUsageData();
    }
  }, [open, tokenId, timeRange]);

  const fetchUsageData = async () => {
    if (!tokenId) return;
    setLoading(true);
    try {
      const res = await apiFetch(`${getApiBase()}/api-tokens/${tokenId}/usage?time_range=${timeRange}`);
      if (res.ok) {
        const newData = await res.json();
        setData(newData);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[85vh]">
        <DrawerHeader>
          <div className="flex items-center justify-between">
            <div>
              <DrawerTitle className="text-base">{tokenName} - {t("usageDetails")}</DrawerTitle>
              <DrawerDescription className="text-xs mt-1">{t("usageTrend")}</DrawerDescription>
            </div>
          </div>
        </DrawerHeader>

        <div className="overflow-y-auto p-4 space-y-4">
          {/* Time Range Selector */}
          <div className="flex gap-2">
            {(["24h", "7d", "30d"] as const).map((range) => (
              <Button
                key={range}
                variant={timeRange === range ? "secondary" : "ghost"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setTimeRange(range)}
              >
                {t(range)}
              </Button>
            ))}
          </div>

          {loading && !data ? (
            <div className="text-center py-8 text-muted-foreground text-sm">{t("loading")}</div>
          ) : data ? (
            <>
              {/* Stats Cards */}
              <div className="grid grid-cols-2 gap-3 relative">
                {loading && (
                  <div className="absolute inset-0 bg-background/50 flex items-center justify-center rounded-lg">
                    <div className="text-xs text-muted-foreground">{t("updating")}</div>
                  </div>
                )}
                <div className="rounded-lg border bg-card p-3">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <Activity className="h-3.5 w-3.5" />
                    <span className="text-xs">{t("totalTokenRequests")}</span>
                  </div>
                  <div className="text-xl font-semibold">{data.total_requests.toLocaleString()}</div>
                </div>
                <div className="rounded-lg border bg-card p-3">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <TrendingUp className="h-3.5 w-3.5" />
                    <span className="text-xs">{t("totalTokens")}</span>
                  </div>
                  <div className="text-xl font-semibold">{data.total_tokens.toLocaleString()}</div>
                </div>
              </div>

              {/* Usage Chart */}
              <div className="rounded-lg border bg-card p-4">
                <h3 className="text-sm font-medium mb-3">{t("usageTrend")}</h3>
                <ChartContainer config={{}} className="h-[200px] w-full">
                  <AreaChart data={data.time_series} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
                    <defs>
                      <linearGradient id="fillTokensDrawer" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS[0]} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS[0]} stopOpacity={0.1}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="time" className="text-xs" interval={0} height={40} />
                    <YAxis className="text-xs" tickFormatter={(value) => {
                      if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
                      if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
                      return value.toString();
                    }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Area 
                      type="monotone" 
                      dataKey="tokens" 
                      name="Tokens"
                      stroke={COLORS[0]} 
                      fill="url(#fillTokensDrawer)"
                      strokeWidth={1}
                    />
                  </AreaChart>
                </ChartContainer>
              </div>

              {/* Model Usage */}
              <div className="rounded-lg border bg-card p-4">
                <h3 className="text-sm font-medium mb-3">{t("byModelStats")}</h3>
                <div className="space-y-2">
                  {data.by_model.slice(0, 5).map((model, index) => (
                    <div key={model.model} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                        <span className="font-mono">{model.model}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="text-[10px]">{model.requests} {t("requests")}</Badge>
                        <span className="text-muted-foreground">{model.tokens.toLocaleString()} tokens</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
