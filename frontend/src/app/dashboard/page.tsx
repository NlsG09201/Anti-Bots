"use client";

import { useCallback, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Shield, Ban, Bot, Users, Activity, Target,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { AttackTimelineChart, RiskHeatmapChart } from "@/components/AttackChart";
import type { HeatmapPoint, TimelinePoint } from "@/components/AttackChart";
import { LiveAlerts } from "@/components/LiveAlerts";
import { api, type Alert, type DashboardCharts, type DashboardStats } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function DashboardPage() {
  const { accessToken } = useAuthStore();
  const queryClient = useQueryClient();
  const [liveAlerts, setLiveAlerts] = useState<Alert[]>([]);
  const [liveStats, setLiveStats] = useState<DashboardStats | null>(null);
  const [liveCharts, setLiveCharts] = useState<DashboardCharts | null>(null);
  const [chartHint, setChartHint] = useState<string | null>(null);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type === "alert" && msg.data) {
        setLiveAlerts((prev) => [msg.data as unknown as Alert, ...prev].slice(0, 20));
        queryClient.invalidateQueries({ queryKey: ["alerts"] });
      }
      if (msg.type === "attack_detected") {
        queryClient.invalidateQueries({ queryKey: ["attacks"] });
      }
      if (msg.type === "stats_update" && msg.data) {
        const d = msg.data;
        const chartsPayload = d.charts as DashboardCharts | undefined;
        setLiveStats({
          active_attacks: Number(d.active_attacks ?? 0),
          total_alerts: Number(d.total_alerts ?? 0),
          blocked_ips: Number(d.blocked_ips ?? 0),
          suspected_bots: Number(d.suspected_bots ?? 0),
          live_viewers: Number(d.live_viewers ?? 0),
          risk_score_avg: Number(d.risk_score_avg ?? 0),
          attacks_last_24h: Number(d.attacks_last_24h ?? 0),
          mitigations_applied: Number(d.mitigations_applied ?? 0),
        });
        if (chartsPayload?.timeline) setLiveCharts(chartsPayload);
      }
    },
    [queryClient],
  );

  useWebSocket(onWsMessage);

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.dashboard.stats(accessToken!),
    enabled: !!accessToken,
  });

  const { data: charts } = useQuery({
    queryKey: ["dashboard-charts"],
    queryFn: () => api.dashboard.charts(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 15000,
  });

  const { data: alerts = [] } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts.list(accessToken!),
    enabled: !!accessToken,
  });

  const { data: attacks = [] } = useQuery({
    queryKey: ["attacks"],
    queryFn: () => api.attacks.list(accessToken!, "active"),
    enabled: !!accessToken,
  });

  const displayStats = liveStats ?? stats;
  const timeline: TimelinePoint[] = liveCharts?.timeline ?? charts?.timeline ?? [];
  const heatmap: HeatmapPoint[] = liveCharts?.heatmap ?? charts?.heatmap ?? [];
  const displayAlerts = liveAlerts.length > 0 ? liveAlerts : alerts;

  useEffect(() => {
    if (charts && !liveCharts) setLiveCharts(charts);
  }, [charts, liveCharts]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Security Overview</h1>
          <p className="text-cyber-muted text-sm mt-1">
            GrÃ¡ficas en tiempo real Â· WebSocket + actualizaciÃ³n cada 15s
          </p>
        </div>
        {charts?.updated_at && (
          <p className="text-xs text-cyber-muted font-mono">
            Datos: {new Date(charts.updated_at).toLocaleTimeString()}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Active Attacks" value={displayStats?.active_attacks ?? 0} icon={AlertTriangle} variant="danger" />
        <StatCard title="Open Alerts" value={displayStats?.total_alerts ?? 0} icon={Shield} variant="warning" />
        <StatCard title="Suspected Bots" value={displayStats?.suspected_bots ?? 0} icon={Bot} variant="danger" />
        <StatCard title="Live Viewers" value={displayStats?.live_viewers ?? 0} icon={Users} variant="success" />
        <StatCard title="Blocked IPs" value={displayStats?.blocked_ips ?? 0} icon={Ban} />
        <StatCard title="Avg Risk Score" value={`${(displayStats?.risk_score_avg ?? 0).toFixed(1)}`} icon={Target} />
        <StatCard title="Attacks (24h)" value={displayStats?.attacks_last_24h ?? 0} icon={Activity} />
        <StatCard title="Mitigations" value={displayStats?.mitigations_applied ?? 0} icon={Shield} variant="success" />
      </div>

      {chartHint && (
        <p className="text-xs text-cyber-accent border border-cyber-accent/30 rounded-lg px-3 py-2">{chartHint}</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">
            Attack Timeline (24h) â€” clic y brush para explorar
          </h3>
          {timeline.length ? (
            <AttackTimelineChart
              data={timeline}
              onTimeSelect={(p) =>
                setChartHint(`${p.time}: ${p.attacks} ataques, ${p.mitigated} mitigados`)
              }
            />
          ) : (
            <p className="text-cyber-muted text-sm py-16 text-center">
              Sin datos aÃºn â€” ingesta eventos o monitorea un canal
            </p>
          )}
        </div>
        <div className="cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Live Alerts</h3>
          <LiveAlerts alerts={displayAlerts.slice(0, 8)} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Risk Heatmap by Hour â€” clic en barra</h3>
          {heatmap.length ? (
            <RiskHeatmapChart
              data={heatmap}
              onHourSelect={(p) =>
                setChartHint(`${p.hour}: riesgo ${p.risk} Â· ${p.events ?? 0} eventos`)
              }
            />
          ) : (
            <p className="text-cyber-muted text-sm py-12 text-center">Sin eventos en las Ãºltimas 24h</p>
          )}
        </div>
        <div className="cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Active Attacks</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-cyber-muted border-b border-cyber-border">
                  <th className="text-left py-2">Type</th>
                  <th className="text-left py-2">Severity</th>
                  <th className="text-right py-2">Risk</th>
                  <th className="text-right py-2">IPs</th>
                </tr>
              </thead>
              <tbody>
                {attacks.slice(0, 8).map((attack) => (
                  <tr key={attack.id} className="border-b border-cyber-border/50 hover:bg-cyber-bg/50">
                    <td className="py-2 text-white capitalize">{attack.attack_type.replace("_", " ")}</td>
                    <td className="py-2">
                      <span className={`text-xs px-2 py-0.5 rounded severity-${attack.severity}`}>
                        {attack.severity}
                      </span>
                    </td>
                    <td className="py-2 text-right font-mono text-cyber-danger">
                      {attack.risk_score.toFixed(0)}
                    </td>
                    <td className="py-2 text-right text-cyber-muted">{attack.source_ips.length}</td>
                  </tr>
                ))}
                {!attacks.length && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-cyber-muted">
                      No active attacks detected
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
