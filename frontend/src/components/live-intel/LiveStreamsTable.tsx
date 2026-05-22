"use client";

import type { LiveStreamSnapshot } from "@/lib/api";
import { PlatformBadge } from "@/components/PlatformBadge";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  snapshots: LiveStreamSnapshot[];
}

export function LiveStreamsTable({ snapshots }: Props) {
  if (!snapshots.length) {
    return (
      <p className="text-sm text-cyber-muted p-6">
        Añade canales externos en Channels (watch) para monitoreo competitivo.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase text-cyber-muted border-b border-cyber-border">
            <th className="px-4 py-2">Canal</th>
            <th className="px-4 py-2">Viewers</th>
            <th className="px-4 py-2">Msg/min</th>
            <th className="px-4 py-2">Engagement</th>
            <th className="px-4 py-2">Growth</th>
            <th className="px-4 py-2">Bot %</th>
            <th className="px-4 py-2">Trust</th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((s) => (
            <tr
              key={s.stream_id}
              className="border-b border-cyber-border/30 hover:bg-cyber-bg/40"
            >
              <td className="px-4 py-2.5">
                <p className="text-white font-medium">{s.channel_name}</p>
                <PlatformBadge platform={s.platform} />
              </td>
              <td className="px-4 py-2.5 tabular-nums text-white">{s.viewers}</td>
              <td className="px-4 py-2.5 tabular-nums">{s.messages_per_minute.toFixed(1)}</td>
              <td className="px-4 py-2.5 tabular-nums">{s.engagement_score.toFixed(0)}</td>
              <td className="px-4 py-2.5 tabular-nums">{s.growth_velocity.toFixed(0)}</td>
              <td className="px-4 py-2.5">
                <Badge variant={s.bot_probability > 0.6 ? "danger" : "muted"}>
                  {(s.bot_probability * 100).toFixed(0)}%
                </Badge>
              </td>
              <td
                className={cn(
                  "px-4 py-2.5 tabular-nums",
                  s.live_trust_score < 40 ? "text-cyber-danger" : "text-cyber-accent",
                )}
              >
                {s.live_trust_score.toFixed(0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
