"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EngagementMetrics } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  metrics: EngagementMetrics | null;
}

function healthColor(score: number): string {
  if (score >= 70) return "text-cyber-accent";
  if (score >= 40) return "text-yellow-400";
  return "text-cyber-danger";
}

export function EngagementHealthPanel({ metrics }: Props) {
  if (!metrics) {
    return (
      <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 p-6 text-cyber-muted text-sm">
        Métricas de engagement pendientes de eventos en vivo.
      </div>
    );
  }

  const chartData = [
    { name: "Viewers", value: metrics.viewers_total },
    { name: "Sospechosos", value: metrics.viewers_suspected },
    { name: "Sin señal sospechosa (est.)", value: metrics.viewers_real_estimate },
    { name: "Chat activo", value: metrics.active_chatters },
    { name: "Chat único", value: metrics.unique_chatters },
  ];

  return (
    <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
            Engagement Health
          </h3>
          <p className="text-xs text-cyber-muted mt-0.5">
            Viewers, chatters y señales de engagement sintético
          </p>
        </div>
        <div className="text-right">
          <p className={cn("text-3xl font-bold tabular-nums", healthColor(metrics.engagement_health_score))}>
            {metrics.engagement_health_score.toFixed(0)}
          </p>
          <p className="text-[10px] text-cyber-muted uppercase">Health score</p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Engagement %" value={`${metrics.engagement_percent.toFixed(1)}%`} />
        <Metric label="Msg / min" value={metrics.messages_per_minute.toFixed(1)} />
        <Metric label="Ratio chat/viewers" value={metrics.viewer_to_chat_ratio.toFixed(4)} />
        <Metric
          label="Señal de engagement sintético"
          value={metrics.synthetic_engagement_score.toFixed(0)}
          danger={metrics.synthetic_engagement_score > 50}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Metric
          label={`Identificados (${metrics.measurement_window_seconds}s)`}
          value={String(metrics.identified_viewers)}
        />
        <Metric
          label="Cobertura observable"
          value={
            metrics.viewer_count_source === "platform"
              ? `${metrics.data_coverage_percent.toFixed(1)}%`
              : "No disponible"
          }
        />
        <Metric label="Calidad de datos" value={`${metrics.data_quality_score.toFixed(0)}/100`} />
      </div>

      <p className="text-xs text-cyber-muted">
        La cobertura compara viewers con evento reciente y el conteo reportado por la
        plataforma. Calidad resume tamaño, frescura y cobertura de la muestra; no es
        una probabilidad de fraude.
      </p>

      {metrics.signals.length > 0 && (
        <ul className="space-y-1 text-xs text-cyber-muted list-disc pl-5">
          {metrics.signals.map((signal) => <li key={signal}>{signal}</li>)}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        {metrics.growth_anomaly && (
          <Badge variant="danger">Anomalía de crecimiento</Badge>
        )}
        {metrics.lexical_diversity > 0 && metrics.lexical_diversity < 0.2 && (
          <Badge variant="warning">Baja diversidad léxica</Badge>
        )}
        {metrics.synthetic_engagement_score > 60 && (
          <Badge variant="danger">Engagement sintético alto</Badge>
        )}
      </div>

      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 10 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: 8,
              }}
            />
            <Bar dataKey="value" fill="#00ff88" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg border border-cyber-border/60 bg-cyber-bg/40 px-3 py-2">
      <p className="text-[10px] text-cyber-muted uppercase">{label}</p>
      <p className={cn("text-lg font-semibold tabular-nums", danger ? "text-cyber-danger" : "text-white")}>
        {value}
      </p>
    </div>
  );
}
