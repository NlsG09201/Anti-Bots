"use client";

import type { LiveIntelOverview } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  heatmap: LiveIntelOverview["heatmap"];
}

export function LiveIntelHeatmap({ heatmap }: Props) {
  if (!heatmap?.length) {
    return (
      <p className="text-sm text-cyber-muted p-4">Sin actividad en vivo para el mapa de calor.</p>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 p-4">
      {heatmap.map((cell) => (
        <div
          key={cell.stream_id}
          className={cn(
            "rounded-lg border p-3 transition-colors",
            cell.intensity >= 70
              ? "border-cyber-danger/50 bg-cyber-danger/15"
              : cell.intensity >= 40
                ? "border-yellow-500/40 bg-yellow-500/10"
                : "border-cyber-accent/30 bg-cyber-accent/10",
          )}
        >
          <p className="text-xs font-medium text-white truncate">{cell.channel}</p>
          <p className="text-[10px] text-cyber-muted uppercase">{cell.platform}</p>
          <p className="text-lg font-bold text-white tabular-nums mt-1">{cell.viewers}</p>
          <p className="text-[10px] text-cyber-muted">intensity {cell.intensity}</p>
        </div>
      ))}
    </div>
  );
}
