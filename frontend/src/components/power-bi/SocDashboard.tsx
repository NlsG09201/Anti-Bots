"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Users, Zap, TrendingUp, Shield } from "lucide-react";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

interface GlobalMetrics {
  timestamp: string;
  total_streams_monitored: number;
  total_suspicious_viewers: number;
  total_attacks_detected: number;
  active_streams: number;
  detected_bots: number;
  suspicious_follows: number;
  engagement_score: number;
  global_threat_score: number;
  alerts_24h: number;
  attacks_24h: number;
}

interface StreamSnapshot {
  stream_id: string;
  platform: string;
  channel_name: string;
  is_live: boolean;
  viewer_count: number;
  engagement_score: number;
  threat_score: number;
  active_attacks: number;
  suspicious_viewer_count: number;
  bot_probability: number;
}

interface KPI {
  name: string;
  label: string;
  value: number;
  target?: number;
  trend?: "up" | "down" | "stable";
  trend_percentage?: number;
  unit: string;
}

interface KPIResponse {
  real_engagement_percentage: KPI;
  bot_percentage: KPI;
  attack_detection_rate: KPI;
  threat_mitigation_rate: KPI;
  platform_health_score: KPI;
  viewers_quality_score: KPI;
  synthetic_audience_percentage: KPI;
  average_response_time: KPI;
}

function MetricCard({
  icon: Icon,
  label,
  value,
  unit,
  trend,
  color = "cyber-accent",
}: {
  icon: any;
  label: string;
  value: number;
  unit: string;
  trend?: "up" | "down";
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-cyber-border/50 bg-cyber-surface/30 p-4 backdrop-blur">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-cyber-muted">{label}</p>
          <p className="mt-2 text-2xl font-bold text-white">
            {value.toLocaleString()}
            <span className="text-sm text-cyber-muted ml-1">{unit}</span>
          </p>
          {trend && (
            <p className={`text-xs mt-1 ${trend === "up" ? "text-red-400" : "text-green-400"}`}>
              {trend === "up" ? "↑" : "↓"} Trend
            </p>
          )}
        </div>
        <div className={`p-2 rounded-lg bg-${color}/10`}>
          <Icon className={`w-5 h-5 text-${color}`} />
        </div>
      </div>
    </div>
  );
}

function KPICard({ kpi }: { kpi: KPI }) {
  const progress = kpi.target ? (kpi.value / kpi.target) * 100 : 0;
  const status = progress >= 90 ? "success" : progress >= 70 ? "warning" : "danger";

  return (
    <div className="rounded-lg border border-cyber-border/50 bg-cyber-surface/30 p-4">
      <p className="text-xs uppercase tracking-wide text-cyber-muted">{kpi.label}</p>
      <div className="mt-3 flex items-end justify-between">
        <div>
          <p className="text-2xl font-bold text-white">
            {kpi.value.toFixed(1)}{kpi.unit}
          </p>
          {kpi.target && (
            <p className="text-xs text-cyber-muted">Target: {kpi.target.toFixed(1)}{kpi.unit}</p>
          )}
        </div>
        <div className="w-16 h-2 rounded-full bg-cyber-surface/50 overflow-hidden">
          <div
            className={`h-full transition-all ${
              status === "success"
                ? "bg-emerald-500"
                : status === "warning"
                ? "bg-amber-500"
                : "bg-red-500"
            }`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function StreamsTable({ streams }: { streams: StreamSnapshot[] }) {
  return (
    <div className="rounded-lg border border-cyber-border/50 bg-cyber-surface/30 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-cyber-border/50 bg-cyber-surface/50">
          <tr>
            <th className="p-3 text-left text-xs font-semibold text-cyber-muted">Channel</th>
            <th className="p-3 text-left text-xs font-semibold text-cyber-muted">Platform</th>
            <th className="p-3 text-right text-xs font-semibold text-cyber-muted">Viewers</th>
            <th className="p-3 text-right text-xs font-semibold text-cyber-muted">Threat</th>
            <th className="p-3 text-right text-xs font-semibold text-cyber-muted">Attacks</th>
            <th className="p-3 text-right text-xs font-semibold text-cyber-muted">Bot %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cyber-border/30">
          {streams.slice(0, 10).map((stream, i) => (
            <tr key={i} className="hover:bg-cyber-surface/50 transition-colors">
              <td className="p-3 text-white font-mono text-xs">{stream.channel_name}</td>
              <td className="p-3 text-cyber-muted capitalize text-xs">{stream.platform}</td>
              <td className="p-3 text-right text-white">{stream.viewer_count.toLocaleString()}</td>
              <td className="p-3 text-right">
                <span
                  className={`inline-block px-2 py-1 rounded text-xs font-mono ${
                    stream.threat_score > 0.7
                      ? "bg-red-500/20 text-red-200"
                      : stream.threat_score > 0.4
                      ? "bg-amber-500/20 text-amber-200"
                      : "bg-green-500/20 text-green-200"
                  }`}
                >
                  {(stream.threat_score * 100).toFixed(0)}
                </span>
              </td>
              <td className="p-3 text-right text-white font-mono">
                {stream.active_attacks > 0 && (
                  <span className="text-red-400 font-bold">{stream.active_attacks}</span>
                )}
              </td>
              <td className="p-3 text-right text-cyber-muted">
                {(stream.bot_probability * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SocDashboard() {
  const token = useApiToken();

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["power-bi", "metrics", "global"],
    queryFn: () =>
      fetch("/api/v1/power-bi/metrics/global", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
    enabled: !!token,
    refetchInterval: 10000,
  });

  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ["power-bi", "metrics", "kpis"],
    queryFn: () =>
      fetch("/api/v1/power-bi/metrics/kpis", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
    enabled: !!token,
    refetchInterval: 15000,
  });

  const { data: streams, isLoading: streamsLoading } = useQuery({
    queryKey: ["power-bi", "streams", "snapshots"],
    queryFn: () =>
      fetch("/api/v1/power-bi/streams/snapshots?limit=100", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
    enabled: !!token,
    refetchInterval: 20000,
  });

  const loading = metricsLoading || kpisLoading || streamsLoading;
  const m = metrics as GlobalMetrics | undefined;
  const k = kpis as KPIResponse | undefined;
  const s = (streams || []) as StreamSnapshot[];

  const threatLevel = useMemo(() => {
    if (!m) return "unknown";
    if (m.global_threat_score > 0.7) return "critical";
    if (m.global_threat_score > 0.5) return "high";
    if (m.global_threat_score > 0.3) return "medium";
    return "low";
  }, [m]);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="border-b border-cyber-border/50 pb-6">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Shield className="w-8 h-8 text-cyber-accent" />
          SOC Dashboard — Anti-Bots Intelligence
        </h1>
        <p className="text-cyber-muted mt-1">
          Real-time threat monitoring • Streaming analytics • AI-powered detection
        </p>
      </div>

      {/* Threat Level Alert */}
      {m && m.global_threat_score > 0.5 && (
        <div
          className={`rounded-lg border p-4 flex items-start gap-3 ${
            threatLevel === "critical"
              ? "border-red-500/50 bg-red-500/10"
              : "border-amber-500/50 bg-amber-500/10"
          }`}
        >
          <AlertTriangle
            className={`w-5 h-5 mt-0.5 flex-shrink-0 ${
              threatLevel === "critical" ? "text-red-400" : "text-amber-400"
            }`}
          />
          <div>
            <p
              className={`font-semibold ${
                threatLevel === "critical" ? "text-red-200" : "text-amber-200"
              }`}
            >
              {threatLevel.toUpperCase()} Threat Level
            </p>
            <p className="text-sm text-cyber-muted mt-1">
              Global threat score: {(m.global_threat_score * 100).toFixed(1)}% •{" "}
              {m.total_attacks_detected} active attacks
            </p>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-cyber-muted">Loading metrics...</div>
      ) : (
        <>
          {/* Global Metrics */}
          {m && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              <MetricCard
                icon={Activity}
                label="Streams Monitored"
                value={m.total_streams_monitored}
                unit="streams"
              />
              <MetricCard
                icon={Users}
                label="Suspicious Viewers"
                value={m.total_suspicious_viewers}
                unit="users"
                trend="up"
              />
              <MetricCard
                icon={AlertTriangle}
                label="Active Attacks"
                value={m.total_attacks_detected}
                unit="events"
              />
              <MetricCard
                icon={Zap}
                label="Bots Detected"
                value={m.detected_bots}
                unit="bots"
              />
            </div>
          )}

          {/* KPIs */}
          {k && (
            <div className="bg-cyber-surface/40 rounded-lg border border-cyber-border/50 p-6">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-cyber-accent" />
                Key Performance Indicators
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                <KPICard kpi={k.real_engagement_percentage} />
                <KPICard kpi={k.bot_percentage} />
                <KPICard kpi={k.threat_mitigation_rate} />
                <KPICard kpi={k.platform_health_score} />
              </div>
            </div>
          )}

          {/* Streams Table */}
          {s.length > 0 && (
            <div className="bg-cyber-surface/40 rounded-lg border border-cyber-border/50 p-6">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyber-accent" />
                Live Streams Overview
              </h2>
              <StreamsTable streams={s} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
