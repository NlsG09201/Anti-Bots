"use client";

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TimelinePoint {
  time: string;
  attacks: number;
  mitigated: number;
}

export interface HeatmapPoint {
  hour: string;
  risk: number;
  events?: number;
}

interface AttackChartProps {
  data: TimelinePoint[];
  onTimeSelect?: (point: TimelinePoint) => void;
}

export function AttackTimelineChart({ data, onTimeSelect }: AttackChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const chartData = useMemo(
    () => data.map((d, i) => ({ ...d, index: i })),
    [data],
  );

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart
        data={chartData}
        onClick={(state) => {
          if (state?.activeTooltipIndex != null) {
            const idx = Number(state.activeTooltipIndex);
            setActiveIndex(idx);
            if (chartData[idx]) onTimeSelect?.(chartData[idx]);
          }
        }}
      >
        <defs>
          <linearGradient id="attackGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ff3366" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#ff3366" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="mitigatedGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#00ff88" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
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
          labelStyle={{ color: "#e2e8f0" }}
        />
        <Legend />
        <Brush dataKey="time" height={24} stroke="#00aaff" fill="#111827" />
        <Area
          type="monotone"
          dataKey="attacks"
          name="Ataques"
          stroke="#ff3366"
          fill="url(#attackGrad)"
          strokeWidth={2}
          activeDot={{ r: 6, fill: "#ff3366" }}
          opacity={activeIndex != null ? 0.85 : 1}
        />
        <Area
          type="monotone"
          dataKey="mitigated"
          name="Mitigados"
          stroke="#00ff88"
          fill="url(#mitigatedGrad)"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RiskHeatmapChart({
  data,
  onHourSelect,
}: {
  data: HeatmapPoint[];
  onHourSelect?: (point: HeatmapPoint) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        data={data}
        onClick={(state) => {
          const idx = state?.activeTooltipIndex;
          if (idx != null && data[Number(idx)]) {
            const point = data[Number(idx)];
            setSelected(point.hour);
            onHourSelect?.(point);
          }
        }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="hour" stroke="#64748b" fontSize={10} />
        <YAxis stroke="#64748b" fontSize={10} domain={[0, 100]} />
        <Tooltip
          contentStyle={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
          formatter={(value: number, _name, item) => {
            const events = (item.payload as HeatmapPoint).events ?? 0;
            return [`${value} riesgo · ${events} eventos`, "Riesgo"];
          }}
        />
        <Bar dataKey="risk" name="Riesgo" radius={[4, 4, 0, 0]} activeBar={{ fill: "#00ff88" }}>
          {data.map((entry) => (
            <Cell
              key={entry.hour}
              fill={selected === entry.hour ? "#00ff88" : riskColor(entry.risk)}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function riskColor(risk: number): string {
  if (risk >= 75) return "#ff3366";
  if (risk >= 50) return "#ffaa00";
  if (risk >= 25) return "#00aaff";
  return "#334155";
}
