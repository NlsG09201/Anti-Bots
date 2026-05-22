"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, AlertTriangle, TrendingUp, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PlatformBadge } from "@/components/PlatformBadge";
import type {
  ViewerFlowOverview,
  ViewerFlowStreamSnapshot,
  ViewerFlowMetrics,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function MetricCard({
  label,
  value,
  sub,
  warn,
}: {
  label: string;
  value: string | number;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        warn
          ? "border-cyber-danger/40 bg-cyber-danger/10"
          : "border-cyber-border/60 bg-cyber-bg/40",
      )}
    >
      <p className="text-[10px] uppercase tracking-widest text-cyber-muted">{label}</p>
      <p className="text-xl font-mono font-semibold text-white mt-1">{value}</p>
      {sub && <p className="text-[10px] text-cyber-muted mt-0.5">{sub}</p>}
    </div>
  );
}

function ThreatBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  return (
    <div className="h-2 rounded-full bg-cyber-bg overflow-hidden">
      <div
        className={cn(
          "h-full transition-all duration-500",
          pct >= 70 ? "bg-cyber-danger" : pct >= 40 ? "bg-orange-500" : "bg-cyber-accent",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function ViewerFlowDashboard({
  overview,
  streamSnap,
  loading,
  onScan,
  streamId,
}: {
  overview?: ViewerFlowOverview;
  streamSnap?: ViewerFlowStreamSnapshot;
  loading?: boolean;
  onScan?: () => void;
  streamId?: string;
}) {
  const metrics: ViewerFlowMetrics | undefined = streamSnap?.metrics;
  const chartData = useMemo(() => {
    const hist = streamSnap?.viewer_history ?? [];
    return hist.map((p, i) => ({
      idx: i,
      viewers: Number(p.count ?? 0),
    }));
  }, [streamSnap?.viewer_history]);

  if (!overview?.enabled && !loading) {
    return (
      <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4 text-sm text-cyber-muted">
        Viewer Flow Intelligence desactivado.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-cyber-accent/20 bg-gradient-to-r from-cyber-surface to-cyber-bg p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Activity className="w-6 h-6 text-cyber-accent" />
            <div>
              <h2 className="text-lg font-bold text-white">Viewer Flow Intelligence</h2>
              <p className="text-xs text-cyber-muted">
                Kick · YouTube Live · TikTok — flujo, raids, viewbots, engagement
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {metrics?.platform && <PlatformBadge platform={metrics.platform} />}
            <Badge variant="info">Live WS</Badge>
            {streamId && onScan && (
              <button
                type="button"
                onClick={onScan}
                className="text-xs px-3 py-1.5 rounded-lg border border-cyber-accent/50 text-cyber-accent hover:bg-cyber-accent/10 cursor-pointer"
              >
                Escanear ahora
              </button>
            )}
          </div>
        </div>
        {overview && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
            <MetricCard label="Streams activos" value={overview.active_non_twitch ?? 0} />
            <MetricCard
              label="Threat global"
              value={`${overview.global_threat_score ?? 0}`}
              warn={(overview.global_threat_score ?? 0) >= 60}
            />
            <MetricCard label="Sospechosos" value={overview.total_suspicious ?? 0} />
            <MetricCard label="Canal" value={metrics?.channel_name || "—"} />
          </div>
        )}
      </div>

      {metrics && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard label="Viewers" value={metrics.viewers_current} />
            <MetricCard
              label="Viewers/min"
              value={(metrics.viewers_per_minute ?? 0).toFixed(1)}
            />
            <MetricCard
              label="Msg/min"
              value={(metrics.messages_per_minute ?? 0).toFixed(1)}
            />
            <MetricCard
              label="Engagement"
              value={`${(metrics.engagement_ratio ?? 0).toFixed(1)}%`}
            />
            <MetricCard
              label="Growth"
              value={(metrics.growth_velocity ?? 0).toFixed(1)}
              warn={(metrics.suspicious_growth_score ?? 0) >= 50}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 rounded-xl border border-cyber-border/80 bg-cyber-surface/30 p-4">
              <p className="text-xs uppercase text-cyber-muted mb-3 flex items-center gap-1">
                <TrendingUp size={14} /> Flujo de audiencia
              </p>
              <div className="h-48">
                {chartData.length > 1 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="idx" hide />
                      <YAxis stroke="#94a3b8" fontSize={10} />
                      <Tooltip
                        contentStyle={{
                          background: "#0f172a",
                          border: "1px solid #334155",
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="viewers"
                        stroke="#22d3ee"
                        fill="#22d3ee33"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-sm text-cyber-muted h-full flex items-center justify-center">
                    Esperando muestras de viewers…
                  </p>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/30 p-4 space-y-3">
              <p className="text-xs uppercase text-cyber-muted">Threat scoring</p>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-cyber-muted">Bot probability</span>
                  <span className="font-mono text-white">
                    {(metrics.bot_probability * 100).toFixed(0)}%
                  </span>
                </div>
                <ThreatBar score={metrics.bot_probability * 100} />
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-cyber-muted">Raid likelihood</span>
                  <span className="font-mono text-white">
                    {(metrics.raid_likelihood * 100).toFixed(0)}%
                  </span>
                </div>
                <ThreatBar score={metrics.raid_likelihood * 100} />
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-cyber-muted">Suspicious growth</span>
                  <span className="font-mono text-white">
                    {metrics.suspicious_growth_score.toFixed(0)}
                  </span>
                </div>
                <ThreatBar score={metrics.suspicious_growth_score} />
              </div>
              {metrics.ai_flags.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-2">
                  {metrics.ai_flags.map((f) => (
                    <span
                      key={f}
                      className="text-[10px] px-2 py-0.5 rounded border border-orange-500/40 text-orange-200"
                    >
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/30 p-4 max-h-64 overflow-y-auto">
          <p className="text-xs uppercase text-cyber-muted mb-2 flex items-center gap-1">
            <Users size={14} /> Timeline de flujo
          </p>
          {loading && (
            <p className="text-xs text-cyber-muted animate-pulse">Cargando…</p>
          )}
          {(streamSnap?.timeline ?? overview?.attack_feed ?? []).map((ev, i) => (
            <div
              key={`${ev.ts}-${i}`}
              className="flex gap-2 py-1.5 border-b border-cyber-border/30 text-xs"
            >
              <span
                className={cn(
                  "shrink-0 uppercase text-[10px] px-1.5 rounded",
                  ev.severity === "critical"
                    ? "text-red-300 bg-red-500/20"
                    : ev.severity === "high"
                      ? "text-orange-200 bg-orange-500/15"
                      : "text-cyber-muted bg-cyber-bg",
                )}
              >
                {ev.kind}
              </span>
              <span className="text-white">{ev.label}</span>
              {ev.username && (
                <span className="text-cyber-muted ml-auto">@{ev.username}</span>
              )}
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/30 p-4 max-h-64 overflow-y-auto">
          <p className="text-xs uppercase text-cyber-muted mb-2 flex items-center gap-1">
            <AlertTriangle size={14} /> Viewers sospechosos
          </p>
          {(streamSnap?.suspicious_viewers ?? []).length === 0 && (
            <p className="text-xs text-cyber-muted">Sin patrones críticos aún.</p>
          )}
          {streamSnap?.suspicious_viewers?.map((v) => (
            <div
              key={v.username}
              className="py-2 border-b border-cyber-border/30 text-xs"
            >
              <div className="flex justify-between">
                <span className="text-white font-medium">@{v.username}</span>
                <span className="font-mono text-cyber-danger">
                  {v.suspicious_score.toFixed(0)}
                </span>
              </div>
              <p className="text-cyber-muted text-[10px] mt-0.5">
                {v.reasons.join(" · ")}
                {v.is_silent ? " · silencioso" : ""}
                {v.cross_platform_hits > 0
                  ? ` · cross-platform×${v.cross_platform_hits}`
                  : ""}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
