"use client";

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
import type { HeatmapPoint, TimelinePoint } from "@/components/AttackChart";

const tooltipStyle = {
  contentStyle: {
    background: "rgba(15, 20, 25, 0.95)",
    border: "1px solid #334155",
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: "#e2e8f0" },
};

interface RealtimeChartsProps {
  timeline: TimelinePoint[];
  heatmap: HeatmapPoint[];
  gateway: { time: string; value: number; label: string }[];
}

export function RealtimeCharts({ timeline, heatmap, gateway }: RealtimeChartsProps) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div className="xl:col-span-2 rounded-xl border border-cyber-border/80 bg-cyber-surface/50 p-4">
        <p className="text-xs uppercase tracking-widest text-cyber-muted mb-3">
          Timeline de ataques (24h)
        </p>
        {timeline.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={timeline}>
              <defs>
                <linearGradient id="atkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ff3366" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#ff3366" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip {...tooltipStyle} />
              <Area
                type="monotone"
                dataKey="attacks"
                stroke="#ff3366"
                fill="url(#atkGrad)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="mitigated"
                stroke="#00ff88"
                fill="transparent"
                strokeWidth={1.5}
                strokeDasharray="4 4"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-cyber-muted py-16 text-center">Sin datos de timeline</p>
        )}
      </div>

      <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/50 p-4">
        <p className="text-xs uppercase tracking-widest text-cyber-muted mb-3">
          Gateway / eventos
        </p>
        {gateway.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={gateway}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" fontSize={9} interval="preserveStartEnd" />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip {...tooltipStyle} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#00aaff"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-cyber-muted py-16 text-center">Sin actividad gateway</p>
        )}
      </div>

      <div className="xl:col-span-3 rounded-xl border border-cyber-border/80 bg-cyber-surface/50 p-4">
        <p className="text-xs uppercase tracking-widest text-cyber-muted mb-3">
          Heatmap de riesgo por hora
        </p>
        {heatmap.length ? (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={heatmap}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="hour" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="risk" fill="#00ff88" radius={[4, 4, 0, 0]} opacity={0.85} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-cyber-muted py-8 text-center">Sin heatmap</p>
        )}
      </div>
    </div>
  );
}
