"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, Zap, BarChart3, Activity } from "lucide-react";
import { cn } from "@/lib/utils";

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

export function TokenStatsView({ data }: { data: TokenStatsData | null }) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 总览卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard title="总请求数" value={data.total_requests.toLocaleString()} icon={BarChart3} />
        <StatCard title="输入 Token" value={data.total_input_tokens.toLocaleString()} icon={TrendingUp} />
        <StatCard title="输出 Token" value={data.total_output_tokens.toLocaleString()} icon={Zap} />
        <StatCard title="总 Token" value={data.total_tokens.toLocaleString()} icon={Activity} />
      </div>

      {/* 模型使用统计 */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="px-6 py-4 border-b border-border">
          <h3 className="text-sm font-semibold">模型使用统计</h3>
        </div>
        <div className="p-6 space-y-4">
          {data.by_model.slice(0, 10).map((item) => {
            const totalTokens = item.input_tokens + item.output_tokens;
            const maxTokens = Math.max(...data.by_model.map(m => m.input_tokens + m.output_tokens));
            const percentage = maxTokens > 0 ? (totalTokens / maxTokens) * 100 : 0;

            return (
              <div key={item.model} className="space-y-1.5">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-medium">{item.model}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {item.requests} 次 · {totalTokens.toLocaleString()} tokens
                  </span>
                </div>
                <div className="h-1.5 w-full bg-secondary/50 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-500"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 账号使用统计 */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="px-6 py-4 border-b border-border">
          <h3 className="text-sm font-semibold">账号使用统计 (Top 10)</h3>
        </div>
        <div className="p-6 space-y-4">
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
