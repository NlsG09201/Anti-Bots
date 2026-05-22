"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LiveStreamSnapshot } from "@/lib/api";

interface Props {
  snapshots: LiveStreamSnapshot[];
}

export function LiveGrowthChart({ snapshots }: Props) {
  const data = snapshots.map((s) => ({
    name: s.channel_name.slice(0, 12),
    viewers: s.viewers,
    engagement: s.engagement_score,
    growth: s.growth_velocity,
  }));

  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-cyber-muted text-sm">
        Sin streams en vivo
      </div>
    );
  }

  return (
    <div className="h-56 p-2">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 10 }} />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 8,
            }}
          />
          <Area
            type="monotone"
            dataKey="viewers"
            stroke="#00ff88"
            fill="#00ff8822"
            name="Viewers"
          />
          <Area
            type="monotone"
            dataKey="growth"
            stroke="#ff6b6b"
            fill="#ff6b6b22"
            name="Growth velocity"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
