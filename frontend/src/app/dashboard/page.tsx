"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, Shield, Ban, Bot, Users, Activity, Target,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { AttackTimelineChart, RiskHeatmapChart } from "@/components/AttackChart";
import { LiveAlerts } from "@/components/LiveAlerts";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useState } from "react";

const mockTimeline = Array.from({ length: 24 }, (_, i) => ({
  time: `${i}:00`,
  attacks: Math.floor(Math.random() * 15),
  mitigated: Math.floor(Math.random() * 10),
}));

const mockHeatmap = Array.from({ length: 24 }, (_, i) => ({
  hour: `${i}h`,
  risk: Math.floor(Math.random() * 100),
}));

export default function DashboardPage() {
  const { accessToken } = useAuthStore();
  const [liveAlerts, setLiveAlerts] = useState<import("@/lib/api").Alert[]>([]);

  useWebSocket((msg) => {
    if (msg.type === "alert" && msg.data) {
      setLiveAlerts((prev) => [msg.data as import("@/lib/api").Alert, ...prev].slice(0, 20));
    }
  });

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.dashboard.stats(accessToken!),
    enabled: !!accessToken,
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

  const displayAlerts = liveAlerts.length > 0 ? liveAlerts : alerts;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Security Overview</h1>
        <p className="text-cyber-muted text-sm mt-1">Real-time threat monitoring and bot detection</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Active Attacks"
          value={stats?.active_attacks ?? 0}
          icon={AlertTriangle}
          variant="danger"
        />
        <StatCard
          title="Open Alerts"
          value={stats?.total_alerts ?? 0}
          icon={Shield}
          variant="warning"
        />
        <StatCard
          title="Suspected Bots"
          value={stats?.suspected_bots ?? 0}
          icon={Bot}
          variant="danger"
        />
        <StatCard
          title="Live Viewers"
          value={stats?.live_viewers ?? 0}
          icon={Users}
          variant="success"
        />
        <StatCard
          title="Blocked IPs"
          value={stats?.blocked_ips ?? 0}
          icon={Ban}
        />
        <StatCard
          title="Avg Risk Score"
          value={`${(stats?.risk_score_avg ?? 0).toFixed(1)}`}
          icon={Target}
        />
        <StatCard
          title="Attacks (24h)"
          value={stats?.attacks_last_24h ?? 0}
          icon={Activity}
        />
        <StatCard
          title="Mitigations"
          value={stats?.mitigations_applied ?? 0}
          icon={Shield}
          variant="success"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Attack Timeline (24h)</h3>
          <AttackTimelineChart data={mockTimeline} />
        </div>
        <div className="cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Live Alerts</h3>
          <LiveAlerts alerts={displayAlerts.slice(0, 8)} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="cyber-card">
          <h3 className="text-sm font-medium text-cyber-muted mb-4">Risk Heatmap by Hour</h3>
          <RiskHeatmapChart data={mockHeatmap} />
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
