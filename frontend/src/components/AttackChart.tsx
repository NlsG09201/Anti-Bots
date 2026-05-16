"use client";

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";

interface AttackChartProps {
  data: { time: string; attacks: number; mitigated: number }[];
}

export function AttackTimelineChart({ data }: AttackChartProps) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="attackGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ff3366" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#ff3366" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={12} />
        <YAxis stroke="#64748b" fontSize={12} />
        <Tooltip
          contentStyle={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 8 }}
          labelStyle={{ color: "#e2e8f0" }}
        />
        <Area type="monotone" dataKey="attacks" stroke="#ff3366" fill="url(#attackGrad)" />
        <Area type="monotone" dataKey="mitigated" stroke="#00ff88" fill="transparent" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RiskHeatmapChart({ data }: { data: { hour: string; risk: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="hour" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: "#111827", border: "1px solid #1e293b" }}
        />
        <Bar dataKey="risk" fill="#00aaff" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
