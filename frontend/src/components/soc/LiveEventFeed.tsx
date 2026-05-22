"use client";

import { Radio } from "lucide-react";
import type { SocLiveFeedEvent } from "@/lib/api";
import { PlatformBadge } from "@/components/PlatformBadge";
import { cn } from "@/lib/utils";

interface LiveEventFeedProps {
  events: SocLiveFeedEvent[];
  liveEvents?: { time: string; label: string; risk: number; platform?: string }[];
}

export function LiveEventFeed({ events, liveEvents = [] }: LiveEventFeedProps) {
  const merged = [
    ...liveEvents.map((e, i) => ({
      id: `ws-${i}-${e.time}`,
      platform: e.platform || "live",
      channel_name: "",
      event_type: e.label,
      platform_username: undefined as string | undefined,
      risk_score: e.risk,
      created_at: e.time,
      is_proxy: false,
    })),
    ...events,
  ].slice(0, 60);

  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/50 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cyber-border/60">
        <div className="flex items-center gap-2">
          <Radio size={16} className="text-cyber-accent animate-pulse" />
          <h3 className="text-sm font-semibold text-white">Live event feed</h3>
        </div>
        <span className="text-[10px] uppercase tracking-widest text-cyber-muted">
          WebSocket
        </span>
      </div>
      <div className="max-h-[420px] overflow-y-auto divide-y divide-cyber-border/40">
        {merged.length === 0 ? (
          <p className="text-sm text-cyber-muted p-6 text-center">
            Esperando eventos de Kick, YouTube y TikTok Live…
          </p>
        ) : (
          merged.map((ev) => (
            <div
              key={ev.id}
              className="px-4 py-2.5 flex items-start gap-3 hover:bg-cyber-bg/40 transition-colors"
            >
              <PlatformBadge platform={ev.platform} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono text-cyber-accent">
                    {ev.event_type}
                  </span>
                  {ev.channel_name && (
                    <span className="text-xs text-cyber-muted truncate">
                      {ev.channel_name}
                    </span>
                  )}
                </div>
                {ev.platform_username && (
                  <p className="text-sm text-white truncate">{ev.platform_username}</p>
                )}
              </div>
              <div className="text-right shrink-0">
                <span
                  className={cn(
                    "text-xs font-mono font-bold tabular-nums",
                    ev.risk_score >= 70
                      ? "text-cyber-danger"
                      : ev.risk_score >= 40
                        ? "text-cyber-warning"
                        : "text-cyber-muted",
                  )}
                >
                  {ev.risk_score.toFixed(0)}
                </span>
                <p className="text-[10px] text-cyber-muted">
                  {ev.created_at.includes("T")
                    ? new Date(ev.created_at).toLocaleTimeString()
                    : ev.created_at}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
