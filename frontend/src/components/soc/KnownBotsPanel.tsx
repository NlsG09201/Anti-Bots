"use client";

import { Bot, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PlatformBadge } from "@/components/PlatformBadge";
import type { TwitchBotsDetection, TwitchBotsOverview } from "@/lib/api";
import { cn } from "@/lib/utils";

const THREAT_STYLES: Record<string, string> = {
  critical: "bg-red-500/20 text-red-300 border-red-500/40",
  high: "bg-orange-500/20 text-orange-300 border-orange-500/40",
  medium: "bg-yellow-500/20 text-yellow-200 border-yellow-500/40",
  low: "bg-cyber-muted/20 text-cyber-muted border-cyber-border",
};

function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg border border-cyber-border/60 bg-cyber-bg/50 p-3">
      <p className="text-[10px] uppercase tracking-widest text-cyber-muted">{label}</p>
      <p className="text-xl font-mono font-semibold text-white mt-1">{value}</p>
    </div>
  );
}

export function KnownBotsPanel({
  overview,
  detections,
  loading,
}: {
  overview?: TwitchBotsOverview;
  detections: TwitchBotsDetection[];
  loading?: boolean;
}) {
  if (!overview?.enabled && !loading) {
    return (
      <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4">
        <p className="text-sm text-cyber-muted">
          TwitchBots.info desactivado (TWITCHBOTS_INFO_ENABLED=false).
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4 backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-cyber-accent" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wide">
            Bots conocidos (TwitchBots.info)
          </h3>
        </div>
        <Badge variant="info">API v2</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Detectados" value={overview?.known_bots_detected ?? 0} />
        <Stat label="Verificaciones" value={overview?.total_verifications ?? 0} />
        <Stat
          label="Perfiles cache"
          value={overview?.global_profiles_cached ?? 0}
        />
        <Stat
          label="MongoDB"
          value={overview?.mongodb ? "activo" : "opcional"}
        />
      </div>

      {overview?.top_bot_types && overview.top_bot_types.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {overview.top_bot_types.map((t) => (
            <span
              key={t.bot_type}
              className="text-xs px-2 py-1 rounded-md border border-cyber-border text-cyber-muted"
            >
              {t.bot_type}: {t.count}
            </span>
          ))}
        </div>
      )}

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {loading && (
          <p className="text-xs text-cyber-muted animate-pulse">Cargando detecciones…</p>
        )}
        {!loading && detections.length === 0 && (
          <p className="text-xs text-cyber-muted">
            Sin bots catalogados detectados en esta ventana. Los viewers se verifican en
            ingest y al escanear chat.
          </p>
        )}
        {detections.map((row, i) => (
          <div
            key={`${row.username}-${row.detected_at ?? i}`}
            className="flex items-center justify-between gap-2 rounded-lg border border-cyber-border/50 bg-cyber-bg/40 px-3 py-2"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">{row.username}</p>
              <p className="text-[10px] text-cyber-muted truncate">
                {row.bot_type || "bot"} · score {Math.round(row.suspicious_score ?? 0)}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <PlatformBadge platform="twitch" />
              <span
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded border uppercase",
                  THREAT_STYLES[row.threat_level] || THREAT_STYLES.medium,
                )}
              >
                <ShieldAlert className="w-3 h-3 inline mr-0.5" />
                {row.threat_level}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
