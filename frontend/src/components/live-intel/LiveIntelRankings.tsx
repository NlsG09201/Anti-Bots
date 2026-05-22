"use client";

import type { StreamRankingEntry } from "@/lib/api";
import { PlatformBadge } from "@/components/PlatformBadge";
import { Badge } from "@/components/ui/badge";

interface Props {
  title: string;
  entries: StreamRankingEntry[];
  variant?: "danger" | "default";
}

export function LiveIntelRankings({ title, entries, variant = "default" }: Props) {
  return (
    <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 overflow-hidden">
      <div className="px-4 py-3 border-b border-cyber-border">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      <div className="divide-y divide-cyber-border/40 max-h-64 overflow-y-auto">
        {entries.length === 0 ? (
          <p className="p-4 text-sm text-cyber-muted">Sin datos en vivo.</p>
        ) : (
          entries.map((e) => (
            <div
              key={`${e.metric}-${e.stream_id}`}
              className="px-4 py-2.5 flex items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-cyber-muted text-xs w-5">#{e.rank}</span>
                <div className="min-w-0">
                  <p className="text-sm text-white truncate">{e.channel_name}</p>
                  <PlatformBadge platform={e.platform} />
                </div>
              </div>
              <Badge variant={variant === "danger" ? "danger" : "default"}>
                {e.score.toFixed(1)}
              </Badge>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
