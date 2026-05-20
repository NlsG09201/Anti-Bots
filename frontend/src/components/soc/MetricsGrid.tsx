"use client";

import {
  Activity,
  AlertTriangle,
  Ban,
  Bot,
  Shield,
  Target,
  Users,
  Zap,
} from "lucide-react";
import type { DashboardStats, SecurityDashboard } from "@/lib/api";
import { cn } from "@/lib/utils";

interface MetricsGridProps {
  stats?: DashboardStats | null;
  security?: SecurityDashboard;
}

function MetricCard({
  label,
  value,
  icon: Icon,
  accent = "default",
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accent?: "default" | "danger" | "warning" | "success" | "info";
}) {
  const accents = {
    default: "border-cyber-border/60",
    danger: "border-cyber-danger/40 bg-cyber-danger/5",
    warning: "border-cyber-warning/40 bg-cyber-warning/5",
    success: "border-cyber-accent/40 bg-cyber-accent/5",
    info: "border-cyber-info/40 bg-cyber-info/5",
  };
  const iconColors = {
    default: "text-cyber-muted",
    danger: "text-cyber-danger",
    warning: "text-cyber-warning",
    success: "text-cyber-accent",
    info: "text-cyber-info",
  };

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border p-4 transition-all hover:shadow-lg hover:shadow-black/40",
        accents[accent],
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      <div className="relative flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-cyber-muted font-medium">
            {label}
          </p>
          <p className="text-2xl font-bold font-mono text-white mt-1 tabular-nums">{value}</p>
        </div>
        <div className={cn("p-2 rounded-lg bg-cyber-bg/80", iconColors[accent])}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
}

export function MetricsGrid({ stats, security }: MetricsGridProps) {
  const s = security?.summary;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
      <MetricCard
        label="Ataques activos"
        value={stats?.active_attacks ?? 0}
        icon={AlertTriangle}
        accent="danger"
      />
      <MetricCard
        label="Alertas"
        value={stats?.total_alerts ?? 0}
        icon={Shield}
        accent="warning"
      />
      <MetricCard
        label="Bots sospechosos"
        value={stats?.suspected_bots ?? 0}
        icon={Bot}
        accent="danger"
      />
      <MetricCard
        label="Viewers live"
        value={stats?.live_viewers ?? 0}
        icon={Users}
        accent="success"
      />
      <MetricCard label="IPs bloqueadas" value={stats?.blocked_ips ?? 0} icon={Ban} />
      <MetricCard
        label="Risk promedio"
        value={(stats?.risk_score_avg ?? 0).toFixed(1)}
        icon={Target}
        accent="warning"
      />
      <MetricCard
        label="Bloqueos 24h"
        value={(s?.blocks_429 ?? 0) + (s?.blocks_403 ?? 0)}
        icon={Zap}
        accent="info"
      />
      <MetricCard
        label="Eventos SOC"
        value={s?.total_events ?? stats?.attacks_last_24h ?? 0}
        icon={Activity}
      />
    </div>
  );
}
