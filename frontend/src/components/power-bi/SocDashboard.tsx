"use client";

import { useMemo, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Brain,
  DatabaseZap,
  Download,
  FileJson,
  FileSpreadsheet,
  RefreshCw,
  Shield,
  Siren,
  Users,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { usePowerBiSocData } from "@/hooks/usePowerBiSocData";

const colors = {
  accent: "#00ff88",
  info: "#00aaff",
  warning: "#ffaa00",
  danger: "#ff3366",
  muted: "#64748b",
};

const windows = [
  { label: "24h", value: 24 },
  { label: "7d", value: 168 },
  { label: "30d", value: 720 },
];

function formatNumber(value?: number, decimals = 0) {
  if (value == null || Number.isNaN(value)) return "0";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

function scoreColor(value?: number) {
  const score = value ?? 0;
  if (score >= 80) return "text-red-300 border-red-500/40 bg-red-500/10";
  if (score >= 60) return "text-orange-300 border-orange-400/40 bg-orange-400/10";
  if (score >= 35) return "text-yellow-300 border-yellow-400/40 bg-yellow-400/10";
  return "text-cyber-accent border-cyber-accent/30 bg-cyber-accent/10";
}

function Panel({
  title,
  icon: Icon,
  children,
  action,
}: {
  title: string;
  icon: ComponentType<{ className?: string; size?: number }>;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-cyber-border/80 bg-cyber-surface/45 p-4 backdrop-blur-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-cyber-accent" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  unit,
  tone = "accent",
}: {
  icon: ComponentType<{ className?: string; size?: number }>;
  label: string;
  value: string;
  unit?: string;
  tone?: keyof typeof colors;
}) {
  const toneClass = {
    accent: "border-cyber-accent/25 bg-cyber-accent/10 text-cyber-accent",
    info: "border-cyber-info/25 bg-cyber-info/10 text-cyber-info",
    warning: "border-cyber-warning/25 bg-cyber-warning/10 text-cyber-warning",
    danger: "border-cyber-danger/25 bg-cyber-danger/10 text-cyber-danger",
    muted: "border-cyber-border bg-cyber-bg/60 text-cyber-muted",
  }[tone];

  return (
    <div className="rounded-lg border border-cyber-border/80 bg-cyber-bg/45 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[11px] uppercase tracking-wider text-cyber-muted">{label}</p>
          <div className="mt-2 flex items-end gap-1">
            <p className="font-mono text-2xl font-semibold text-white">{value}</p>
            {unit && <span className="pb-1 text-xs text-cyber-muted">{unit}</span>}
          </div>
        </div>
        <div className={`rounded-md border p-2 ${toneClass}`}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-cyber-border/70 bg-cyber-bg/30 text-sm text-cyber-muted">
      {label}
    </div>
  );
}

export function SocDashboard() {
  const [hours, setHours] = useState(168);
  const {
    accessToken,
    overview,
    live,
    streams,
    attacks,
    ai,
    engagement,
    suspicious,
    metadata,
    executive,
    loading,
    error,
    sync,
    refresh,
  } = usePowerBiSocData(hours);

  const global = overview?.metrics_globales;
  const realtime = overview?.metricas_tiempo_real;
  const streamRows = streams?.streams ?? [];
  const topThreatStreams = live?.top_streams ?? overview?.kpis.streams_mas_sospechosos ?? [];
  const platformRows = streams?.platform_summary ?? [];
  const aiPredictions = ai?.predictions ?? [];
  const attackTimeline = attacks?.timeline ?? [];
  const chatRows = engagement?.chat_activity ?? [];
  const metadataTables = metadata?.tables ?? [];

  const threatSeries = useMemo(
    () =>
      topThreatStreams.slice(0, 10).map((row) => ({
        channel: row.channel_name,
        threat: row.threat_score,
        suspicious: Math.round(row.suspicious_ratio * 100),
        viewers: row.viewer_count,
      })),
    [topThreatStreams],
  );

  const platformChart = useMemo(
    () =>
      platformRows.map((row) => ({
        platform: row.platform_name,
        viewers: row.viewer_count,
        attacks: row.active_attacks,
        threat: row.threat_score,
      })),
    [platformRows],
  );

  const aiScatter = useMemo(
    () =>
      aiPredictions.slice(0, 12).map((row) => ({
        channel: row.channel_name,
        bot: row.bot_probability,
        anomaly: row.anomaly_score,
        coordination: row.coordination_score,
      })),
    [aiPredictions],
  );

  const chatTimeline = useMemo(
    () =>
      chatRows.slice(-24).map((row) => ({
        bucket: String(row.bucket_start).slice(5, 16).replace("T", " "),
        messages: row.messages,
        suspicious: row.suspicious_messages,
        risk: row.message_risk_avg,
      })),
    [chatRows],
  );

  async function downloadExport(kind: "json" | "excel" | "powerbi-package") {
    if (!accessToken) return;
    const path =
      kind === "powerbi-package"
        ? `/api/v1/analytics/exports/powerbi-package?hours=${hours}`
        : `/api/v1/analytics/exports/${kind}?hours=${hours}`;
    const response = await fetch(path, {
      headers: { Authorization: `Bearer ${accessToken}` },
      credentials: "include",
    });
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download =
      kind === "excel"
        ? "streamshield-analytics.xlsx"
        : kind === "json"
          ? "streamshield-analytics.json"
          : "streamshield-powerbi-package.zip";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-200">
        No se pudo cargar analytics Power BI. Revisa sesion, permisos y API backend.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-cyber-border/80 bg-cyber-surface/50 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex items-center gap-3">
              <div className="rounded-lg border border-cyber-accent/25 bg-cyber-accent/10 p-2">
                <Shield className="h-6 w-6 text-cyber-accent" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  Power BI SOC Analytics
                </h1>
                <p className="text-sm text-cyber-muted">
                  Datasets, DAX, reporte ejecutivo, streaming analytics e inteligencia anti-bots en vivo.
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-cyber-border bg-cyber-bg/60 p-1">
              {windows.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setHours(item.value)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    hours === item.value
                      ? "bg-cyber-accent text-cyber-bg"
                      : "text-cyber-muted hover:text-white"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw size={14} />
              Refresh
            </Button>
            <Button size="sm" onClick={() => sync.mutate()} disabled={sync.isPending}>
              <DatabaseZap size={14} />
              {sync.isPending ? "Syncing" : "Sync Power BI"}
            </Button>
          </div>
        </div>
      </header>

      {sync.data && (
        <div className="rounded-lg border border-cyber-info/30 bg-cyber-info/10 p-4 text-sm text-cyber-info">
          {sync.data.configured
            ? `Power BI dataset synced: ${sync.data.tables_pushed?.length ?? 0} tables pushed.`
            : sync.data.message ?? "Power BI Service credentials are not configured."}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg border border-cyber-border bg-cyber-surface/40 p-8 text-center text-sm text-cyber-muted">
          Loading SOC analytics warehouse...
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard
              icon={Users}
              label="Viewers monitored"
              value={formatNumber(global?.viewers_monitoreados)}
              tone="info"
            />
            <MetricCard
              icon={Bot}
              label="Suspicious viewers"
              value={formatNumber(global?.viewers_sospechosos)}
              tone="warning"
            />
            <MetricCard
              icon={Siren}
              label="Attacks detected"
              value={formatNumber(global?.ataques_detectados)}
              tone="danger"
            />
            <MetricCard
              icon={Activity}
              label="Active streams"
              value={formatNumber(global?.streams_activos)}
              tone="accent"
            />
            <MetricCard
              icon={Shield}
              label="Global risk"
              value={formatNumber(global?.riesgo_global, 1)}
              unit="/100"
              tone={(global?.riesgo_global ?? 0) >= 60 ? "danger" : "accent"}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
            <div className="xl:col-span-8">
              <Panel
                title="SOC Overview"
                icon={BarChart3}
                action={<Badge variant={(global?.riesgo_global ?? 0) >= 60 ? "danger" : "default"}>{executive?.executive_summary.posture ?? "stable"}</Badge>}
              >
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                  <div className="lg:col-span-2">
                    {threatSeries.length ? (
                      <div className="h-[270px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={threatSeries}>
                            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                            <XAxis dataKey="channel" stroke={colors.muted} tick={{ fontSize: 11 }} />
                            <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                            <Tooltip
                              contentStyle={{ background: "#0f1419", border: "1px solid #1e293b" }}
                              labelStyle={{ color: "#e2e8f0" }}
                            />
                            <Area type="monotone" dataKey="threat" stroke={colors.danger} fill="#ff336633" name="Threat score" />
                            <Area type="monotone" dataKey="suspicious" stroke={colors.warning} fill="#ffaa0022" name="Suspicious %" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <EmptyState label="No threat score rows in this window." />
                    )}
                  </div>
                  <div className="space-y-3">
                    <MetricCard icon={Zap} label="Viewers/min" value={formatNumber(realtime?.viewers_por_minuto, 2)} tone="info" />
                    <MetricCard icon={Activity} label="Messages/min" value={formatNumber(realtime?.mensajes_por_minuto, 2)} tone="accent" />
                    <MetricCard icon={AlertTriangle} label="Anomalies" value={formatNumber(realtime?.anomalias)} tone="warning" />
                  </div>
                </div>
              </Panel>
            </div>

            <div className="xl:col-span-4">
              <Panel title="Executive Report" icon={FileJson}>
                <div className="space-y-4">
                  <div className={`rounded-lg border p-4 ${scoreColor(executive?.executive_summary.global_risk)}`}>
                    <p className="text-xs uppercase tracking-wider opacity-80">Recommendation</p>
                    <p className="mt-2 text-sm leading-6 text-white">
                      {executive?.executive_summary.recommendation ?? "Analytics report is ready for review."}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <MetricCard icon={Brain} label="AI risk avg" value={formatNumber(ai?.summary.threat_score_avg, 1)} tone="danger" />
                    <MetricCard icon={Bot} label="Bot probability" value={formatNumber(ai?.summary.bot_probability_avg, 1)} tone="warning" />
                  </div>
                </div>
              </Panel>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Panel title="Cross Platform Analysis" icon={DatabaseZap}>
              {platformChart.length ? (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={platformChart}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="platform" stroke={colors.muted} tick={{ fontSize: 11 }} />
                      <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: "#0f1419", border: "1px solid #1e293b" }} />
                      <Bar dataKey="viewers" name="Viewers" fill={colors.info} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="attacks" name="Active attacks" fill={colors.danger} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyState label="No platform rows available." />
              )}
            </Panel>

            <Panel title="Threat Timeline" icon={Siren}>
              {attackTimeline.length ? (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={attackTimeline}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="bucket" stroke={colors.muted} tick={{ fontSize: 11 }} />
                      <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: "#0f1419", border: "1px solid #1e293b" }} />
                      <Line type="monotone" dataKey="attacks" stroke={colors.danger} strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="avg_risk" stroke={colors.warning} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyState label="No attacks registered in this window." />
              )}
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
            <div className="xl:col-span-7">
              <Panel title="AI Predictions" icon={Brain}>
                {aiScatter.length ? (
                  <div className="h-[280px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={aiScatter}>
                        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                        <XAxis dataKey="channel" stroke={colors.muted} tick={{ fontSize: 11 }} />
                        <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                        <Tooltip contentStyle={{ background: "#0f1419", border: "1px solid #1e293b" }} />
                        <Bar dataKey="bot" name="Bot probability" fill={colors.warning} radius={[4, 4, 0, 0]} />
                        <Bar dataKey="anomaly" name="Anomaly score" fill={colors.danger} radius={[4, 4, 0, 0]} />
                        <Bar dataKey="coordination" name="Coordination" fill={colors.info} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <EmptyState label="No AI prediction rows available." />
                )}
              </Panel>
            </div>
            <div className="xl:col-span-5">
              <Panel title="Chat And Engagement" icon={Activity}>
                {chatTimeline.length ? (
                  <div className="h-[280px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chatTimeline}>
                        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                        <XAxis dataKey="bucket" stroke={colors.muted} tick={{ fontSize: 11 }} />
                        <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                        <Tooltip contentStyle={{ background: "#0f1419", border: "1px solid #1e293b" }} />
                        <Area type="monotone" dataKey="messages" stroke={colors.accent} fill="#00ff8830" name="Messages" />
                        <Area type="monotone" dataKey="suspicious" stroke={colors.danger} fill="#ff336630" name="Suspicious messages" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <EmptyState label="No chat activity rows available." />
                )}
              </Panel>
            </div>
          </div>

          <Panel
            title="Power BI Dataset And Exports"
            icon={FileSpreadsheet}
            action={
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => downloadExport("json")}>
                  <FileJson size={14} />
                  JSON
                </Button>
                <Button variant="outline" size="sm" onClick={() => downloadExport("excel")}>
                  <FileSpreadsheet size={14} />
                  Excel
                </Button>
                <Button variant="outline" size="sm" onClick={() => downloadExport("powerbi-package")}>
                  <Download size={14} />
                  Package
                </Button>
              </div>
            }
          >
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <div className="xl:col-span-2 overflow-x-auto rounded-lg border border-cyber-border/70">
                <table className="w-full min-w-[780px] text-sm">
                  <thead className="bg-cyber-bg/70 text-xs uppercase tracking-wider text-cyber-muted">
                    <tr>
                      <th className="px-3 py-3 text-left">Dataset</th>
                      <th className="px-3 py-3 text-right">Rows</th>
                      <th className="px-3 py-3 text-right">Columns</th>
                      <th className="px-3 py-3 text-left">Power BI mode</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cyber-border/60">
                    {metadataTables.map((table) => (
                      <tr key={table.name} className="hover:bg-cyber-bg/50">
                        <td className="px-3 py-3 font-mono text-xs text-white">{table.name}</td>
                        <td className="px-3 py-3 text-right font-mono text-cyber-accent">{formatNumber(table.rows)}</td>
                        <td className="px-3 py-3 text-right text-cyber-muted">{table.columns.length}</td>
                        <td className="px-3 py-3 text-cyber-muted">Push dataset / import package</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="space-y-3">
                <MetricCard icon={DatabaseZap} label="Tables" value={formatNumber(metadataTables.length)} tone="info" />
                <MetricCard icon={BarChart3} label="DAX measures" value={formatNumber(Object.keys(metadata?.measures ?? {}).length)} tone="accent" />
                <MetricCard icon={FileJson} label="Report pages" value={formatNumber(metadata?.report_pages.length)} tone="warning" />
              </div>
            </div>
          </Panel>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Panel title="Top Suspicious Viewers" icon={Bot}>
              <div className="max-h-[330px] overflow-auto rounded-lg border border-cyber-border/70">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="sticky top-0 bg-cyber-bg text-xs uppercase tracking-wider text-cyber-muted">
                    <tr>
                      <th className="px-3 py-3 text-left">Viewer</th>
                      <th className="px-3 py-3 text-left">Channel</th>
                      <th className="px-3 py-3 text-left">Platform</th>
                      <th className="px-3 py-3 text-right">Risk</th>
                      <th className="px-3 py-3 text-left">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cyber-border/60">
                    {(suspicious?.top_viewers ?? []).slice(0, 12).map((viewer) => (
                      <tr key={viewer.viewer_session_id} className="hover:bg-cyber-bg/50">
                        <td className="px-3 py-3 font-mono text-xs text-white">{viewer.platform_username || "unknown"}</td>
                        <td className="px-3 py-3 text-cyber-muted">{viewer.channel_name}</td>
                        <td className="px-3 py-3 uppercase text-cyber-muted">{viewer.platform_key}</td>
                        <td className="px-3 py-3 text-right">
                          <span className={`rounded-md border px-2 py-1 font-mono text-xs ${scoreColor(viewer.risk_score)}`}>
                            {formatNumber(viewer.risk_score, 1)}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-cyber-muted">{viewer.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Streams Most At Risk" icon={AlertTriangle}>
              <div className="max-h-[330px] overflow-auto rounded-lg border border-cyber-border/70">
                <table className="w-full min-w-[660px] text-sm">
                  <thead className="sticky top-0 bg-cyber-bg text-xs uppercase tracking-wider text-cyber-muted">
                    <tr>
                      <th className="px-3 py-3 text-left">Channel</th>
                      <th className="px-3 py-3 text-left">Platform</th>
                      <th className="px-3 py-3 text-right">Viewers</th>
                      <th className="px-3 py-3 text-right">Threat</th>
                      <th className="px-3 py-3 text-right">Attacks</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cyber-border/60">
                    {streamRows.slice(0, 12).map((stream) => (
                      <tr key={stream.stream_id} className="hover:bg-cyber-bg/50">
                        <td className="px-3 py-3 font-mono text-xs text-white">{stream.channel_name}</td>
                        <td className="px-3 py-3 uppercase text-cyber-muted">{stream.platform_key}</td>
                        <td className="px-3 py-3 text-right font-mono text-white">{formatNumber(stream.viewer_count)}</td>
                        <td className="px-3 py-3 text-right">
                          <span className={`rounded-md border px-2 py-1 font-mono text-xs ${scoreColor(stream.threat_score)}`}>
                            {formatNumber(stream.threat_score, 1)}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-right text-cyber-muted">
                          {formatNumber(topThreatStreams.find((row) => row.stream_id === stream.stream_id)?.active_attacks ?? 0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
