"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface SecurityTimelinePoint {
  time: string;
  blocks?: number;
  events?: number;
  high_risk?: number;
  proxy?: number;
}

interface Props {
  gateway: SecurityTimelinePoint[];
  events: SecurityTimelinePoint[];
}

export function SecurityBlocksChart({ gateway }: { gateway: SecurityTimelinePoint[] }) {
  const data = useMemo(() => gateway, [gateway]);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="blockGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
        />
        <Area
          type="monotone"
          dataKey="blocks"
          name="Bloqueos gateway"
          stroke="#f59e0b"
          fill="url(#blockGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SecurityEventsChart({ events }: { events: SecurityTimelinePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={events}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
        />
        <Legend />
        <Bar dataKey="events" name="Eventos" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        <Bar dataKey="proxy" name="Proxy" fill="#ef4444" radius={[4, 4, 0, 0]} />
        <Bar dataKey="high_risk" name="Alto riesgo" fill="#a855f7" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
