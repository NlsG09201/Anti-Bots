"use client";

import type { ThreatEntitySummary, ThreatIntelAssessment } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

interface Props {
  topEntities: ThreatEntitySummary[];
  liveAssessment: ThreatIntelAssessment | null;
}

export function ThreatIntelLiveFeed({ topEntities, liveAssessment }: Props) {
  return (
    <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 overflow-hidden">
      <div className="px-4 py-3 border-b border-cyber-border flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Live Threat Feed</h3>
        <Badge variant="default">TI Engine</Badge>
      </div>

      {liveAssessment?.ai_insights?.length ? (
        <div className="px-4 py-3 border-b border-cyber-border/60 bg-cyber-accent/5">
          <p className="text-[10px] uppercase text-cyber-accent mb-2">AI Insights</p>
          <ul className="space-y-1 text-xs text-cyber-muted">
            {liveAssessment.ai_insights.map((line, i) => (
              <li key={i} className="text-white/90">
                {line}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2 mt-2 text-[10px]">
            <span>Bot P: {(liveAssessment.bot_probability * 100).toFixed(0)}%</span>
            <span>Coord: {(liveAssessment.coordination_score * 100).toFixed(0)}%</span>
            <span>Raid: {(liveAssessment.raid_likelihood * 100).toFixed(0)}%</span>
          </div>
        </div>
      ) : null}

      <div className="max-h-64 overflow-y-auto divide-y divide-cyber-border/40">
        {topEntities.length === 0 ? (
          <p className="p-4 text-sm text-cyber-muted">Sin entidades en la base global aún.</p>
        ) : (
          topEntities.map((e) => (
            <div key={e.entity_key} className="px-4 py-2.5 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm text-white truncate">
                  {e.username || e.entity_key.slice(0, 12)}
                </p>
                <p className="text-[10px] text-cyber-muted">
                  {e.platform || "—"} · threat {e.threat_score?.toFixed?.(0) ?? e.threat_score}
                </p>
              </div>
              <Badge variant={e.bot_probability > 0.6 ? "danger" : "muted"}>
                {(e.bot_probability * 100).toFixed(0)}% bot
              </Badge>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
