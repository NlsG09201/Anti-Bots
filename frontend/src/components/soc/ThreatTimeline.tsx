"use client";

import type { TimelineEntry } from "@/hooks/useSocData";
import { cn } from "@/lib/utils";

const severityStyles = {
  critical: "bg-cyber-danger border-cyber-danger",
  high: "bg-orange-500 border-orange-500",
  medium: "bg-cyber-warning border-cyber-warning",
  low: "bg-cyber-info border-cyber-info",
};

export function ThreatTimeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/50 p-4 h-full min-h-[320px] flex flex-col">
      <p className="text-xs uppercase tracking-widest text-cyber-muted mb-4">Threat timeline</p>
      <div className="flex-1 overflow-y-auto space-y-0 pr-1 max-h-[380px]">
        {entries.length ? (
          entries.map((e, i) => (
            <div key={e.id} className="relative pl-6 pb-5 last:pb-0">
              {i < entries.length - 1 && (
                <span className="absolute left-[7px] top-3 bottom-0 w-px bg-cyber-border" />
              )}
              <span
                className={cn(
                  "absolute left-0 top-1.5 w-3.5 h-3.5 rounded-full border-2",
                  severityStyles[e.severity],
                )}
              />
              <p className="text-[10px] font-mono text-cyber-muted">{e.time}</p>
              <p className="text-sm font-medium text-white mt-0.5">{e.title}</p>
              <p className="text-xs text-cyber-muted mt-0.5 line-clamp-2">{e.detail}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-cyber-muted text-center py-16">Sin eventos recientes</p>
        )}
      </div>
    </div>
  );
}
