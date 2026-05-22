"use client";

import type { SocOverview } from "@/lib/api";
import { PlatformBadge } from "@/components/PlatformBadge";
import { cn } from "@/lib/utils";

const PLATFORM_ORDER = ["kick", "youtube", "tiktok", "twitch"] as const;

const THREAT_STYLES = {
  low: "text-cyber-accent border-cyber-accent/40",
  medium: "text-cyber-warning border-cyber-warning/40",
  high: "text-orange-400 border-orange-500/40",
  critical: "text-cyber-danger border-cyber-danger/50",
};

interface PlatformSocPanelProps {
  soc?: SocOverview | null;
}

export function PlatformSocPanel({ soc }: PlatformSocPanelProps) {
  if (!soc) return null;

  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-cyber-muted">
            Threat level
          </p>
          <p
            className={cn(
              "text-2xl font-bold font-mono uppercase",
              THREAT_STYLES[soc.threat_level],
            )}
          >
            {soc.threat_level}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-widest text-cyber-muted">
            Threat score
          </p>
          <p className="text-3xl font-bold font-mono text-white tabular-nums">
            {soc.threat_score}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {PLATFORM_ORDER.filter((p) => soc.platforms[p]).map((platform) => {
          const m = soc.platforms[platform];
          return (
            <div
              key={platform}
              className="rounded-lg border border-cyber-border/50 bg-cyber-bg/50 p-3 space-y-2"
            >
              <PlatformBadge platform={platform} />
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="text-cyber-muted">Live</p>
                  <p className="font-mono text-white">{m.live_streams}</p>
                </div>
                <div>
                  <p className="text-cyber-muted">Viewers</p>
                  <p className="font-mono text-white">{m.viewers}</p>
                </div>
                <div>
                  <p className="text-cyber-muted">Sospechosos</p>
                  <p className="font-mono text-cyber-warning">{m.suspected}</p>
                </div>
                <div>
                  <p className="text-cyber-muted">Ataques</p>
                  <p className="font-mono text-cyber-danger">{m.active_attacks}</p>
                </div>
              </div>
              <p className="text-[10px] text-cyber-muted">
                {m.events_1h} eventos / 1h
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
