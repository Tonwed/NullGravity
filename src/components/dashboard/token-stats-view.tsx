"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, Zap, BarChart3, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ChartContainer } from "@/components/ui/chart";
import { Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";

const COLORS = [
  "#3b82f6", // 蓝色
  "#10b981", // 绿色
  "#f59e0b", // 橙色
  "#8b5cf6", // 紫色
  "#ef4444", // 红色
  "#06b6d4", // 青色
  "#f97316", // 深橙
  "#a855f7", // 深紫
  "#ec4899", // 粉色
  "#14b8a6", // 青绿
];

const CustomTooltip = ({ active, payload, label, seriesKeys }: any) => {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="rounded-lg border bg-background p-2 shadow-sm">
      <div className="text-xs font-medium mb-1">{label}</div>
      {payload.map((entry: any, index: number) => {
        // 优先使用 stroke，然后 fill，最后使用 COLORS 数组
        let color = entry.stroke || entry.fill;
        if (!color || color === '#000' || color === '#000000') {
          const seriesIndex = seriesKeys?.indexOf(entry.dataKey) ?? index;
          color = COLORS[seriesIndex % COLORS.length];
        }
        return (
          <div key={entry.dataKey} className="flex items-center gap-2 text-xs">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-muted-foreground">{entry.name || entry.dataKey}:</span>
            <span className="font-medium">{entry.value.toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
};

interface TokenStatsData {
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  by_model: Array<{
    model: string;
    requests: number;
    input_tokens: number;
    output_tokens: number;
  }>;
  by_account: Array<{
    email: string;
    requests: number;
    input_tokens: number;
    output_tokens: number;
  }>;
  top_models: Array<{ model: string; count: number }>;
  time_series: Array<{ time: string; [key: string]: any }>;
  series_keys: string[];
}

function StatCard({ title, value, icon: Icon }: { title: string; value: string | number; icon: React.ElementType }) {
  return (
    <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none px-4 py-3 transition-colors hover:bg-accent/5">
      <div className="flex items-center justify-between space-y-0 mb-1">
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide opacity-80">{title}</p>
        <Icon className="h-3.5 w-3.5 text-muted-foreground opacity-50" />
      </div>
      <div className="text-xl font-bold tracking-tight leading-none pt-0.5">{value}</div>
    </div>
  );
}

export function TokenStatsView({ data, onGroupByChange }: { 
  data: TokenStatsData | null; 
  onGroupByChange: (groupBy: string) => void;
}) {
  const [groupBy, setGroupBy] = useState<"total" | "model" | "user" | "account">("total");

  const handleGroupByChange = (newGroupBy: "total" | "model" | "user" | "account") => {
    setGroupBy(newGroupBy);
    onGroupByChange(newGroupBy);
  };

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    );
  }

  // 检查是否有数据
  const hasData = data.total_requests > 0;

  if (!hasData) {
    return (
      <div className="flex flex-col items-center justify-center h-[400px] space-y-4">
        <BarChart3 className="h-16 w-16 text-muted-foreground/20" />
        <div className="text-center space-y-2">
          <h3 className="text-lg font-semibold">暂无统计数据</h3>
          <p className="text-sm text-muted-foreground max-w-sm">
            请先在 API 代理页面启动代理服务，然后通过客户端发送请求，即可查看 Token 使用统计
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* 总览卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard title="总请求数" value={data.total_requests.toLocaleString()} icon={BarChart3} />
        <StatCard title="输入 Token" value={data.total_input_tokens.toLocaleString()} icon={TrendingUp} />
        <StatCard title="输出 Token" value={data.total_output_tokens.toLocaleString()} icon={Zap} />
        <StatCard title="总 Token" value={data.total_tokens.toLocaleString()} icon={Activity} />
      </div>

      {/* 模型使用统计 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-sm font-medium">模型使用统计</h3>
          <div className="flex gap-2">
            <Button 
              variant={groupBy === "total" ? "secondary" : "ghost"} 
              size="sm" 
              className="h-7 text-xs"
              onClick={() => handleGroupByChange("total")}
            >
              总体
            </Button>
            <Button 
              variant={groupBy === "model" ? "secondary" : "ghost"} 
              size="sm" 
              className="h-7 text-xs"
              onClick={() => handleGroupByChange("model")}
            >
              按模型
            </Button>
            <Button 
              variant={groupBy === "user" ? "secondary" : "ghost"} 
              size="sm" 
              className="h-7 text-xs"
              onClick={() => handleGroupByChange("user")}
            >
              按Token
            </Button>
            <Button 
              variant={groupBy === "account" ? "secondary" : "ghost"} 
              size="sm" 
              className="h-7 text-xs"
              onClick={() => handleGroupByChange("account")}
            >
              按账号
            </Button>
          </div>
        </div>
        <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-6">
          <ChartContainer
            config={{}}
            className="h-[300px] w-full"
          >
            <AreaChart data={data.time_series} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
              <defs>
                {data.series_keys.map((key, index) => (
                  <linearGradient key={key} id={`fill${index}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS[index % COLORS.length]} stopOpacity={0.8}/>
                    <stop offset="95%" stopColor={COLORS[index % COLORS.length]} stopOpacity={0.1}/>
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="time" className="text-xs" interval={0} height={40} />
              <YAxis 
                className="text-xs"
                tickFormatter={(value) => {
                  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
                  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
                  return value.toString();
                }}
              />
              <Tooltip content={<CustomTooltip seriesKeys={data.series_keys} />} />
              {data.series_keys.map((key, index) => (
                <Area 
                  key={key}
                  type="monotone" 
                  dataKey={key}
                  stroke={COLORS[index % COLORS.length]}
                  fill={`url(#fill${index})`}
                  strokeWidth={2}
                />
              ))}
            </AreaChart>
          </ChartContainer>
        </div>
      </div>

      {/* 账号使用统计 */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium px-1">账号使用统计 (Top 10)</h3>
        <div className="rounded-lg border border-border border-b-border/80 bg-card shadow-[0_2px_4px_-2px_rgba(0,0,0,0.08)] dark:shadow-none p-6 space-y-4">
          {data.by_account.map((item) => {
          const totalTokens = item.input_tokens + item.output_tokens;
          const maxTokens = Math.max(...data.by_account.map(a => a.input_tokens + a.output_tokens));
          const percentage = maxTokens > 0 ? (totalTokens / maxTokens) * 100 : 0;

          return (
            <div key={item.email} className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="font-medium truncate max-w-[60%]">{item.email}</span>
                <span className="text-muted-foreground tabular-nums whitespace-nowrap">
                  {item.requests} 次 · {totalTokens.toLocaleString()} tokens
                </span>
              </div>
              <div className="h-1.5 w-full bg-secondary/50 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          );
        })}
        </div>
      </div>
    </div>
  );
}
