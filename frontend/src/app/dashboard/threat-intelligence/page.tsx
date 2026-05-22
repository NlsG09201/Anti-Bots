"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, GitBranch, Radar, Shield, type LucideIcon } from "lucide-react";
import { EngagementHealthPanel } from "@/components/threat-intel/EngagementHealthPanel";
import { ThreatGraphCytoscape } from "@/components/threat-intel/ThreatGraphCytoscape";
import { ThreatIntelLiveFeed } from "@/components/threat-intel/ThreatIntelLiveFeed";
import { Badge } from "@/components/ui/badge";
import { useThreatIntel } from "@/hooks/useThreatIntel";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useSocData } from "@/hooks/useSocData";
import { cn } from "@/lib/utils";

export default function ThreatIntelligencePage() {
  const accessToken = useApiToken();
  const { liveStream, connected } = useSocData();
  const streamId = liveStream?.id;

  const {
    overview,
    overviewLoading,
    displayEngagement,
    displayGraph,
    liveAssessment,
    topEntities,
  } = useThreatIntel(streamId);

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!),
    enabled: !!accessToken,
  });

  const liveCount = useMemo(() => streams.filter((s) => s.is_live).length, [streams]);

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-cyber-danger/20 bg-gradient-to-br from-cyber-surface via-cyber-bg to-cyber-surface p-6 md:p-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Radar className="text-cyber-danger" size={28} />
              <h1 className="text-2xl md:text-3xl font-bold text-white">
                Threat Intelligence
              </h1>
            </div>
            <p className="text-cyber-muted text-sm max-w-2xl">
              Motor global de inteligencia: reputación, engagement health, huellas léxicas,
              correlación cross-platform y grafos de botnets en tiempo real.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={connected ? "default" : "muted"}>
              WebSocket {connected ? "live" : "offline"}
            </Badge>
            <Badge variant={overview?.enabled ? "default" : "warning"}>
              MongoDB {overview?.enabled ? "activo" : "requerido"}
            </Badge>
            <Badge variant="muted">{liveCount} streams live</Badge>
          </div>
        </div>
      </div>

      {!overviewLoading && overview && !overview.enabled && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
          {overview.message ||
            "Configura MONGODB_URI en Render para persistir la base global de amenazas."}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Shield}
          label="Entidades TI"
          value={overview?.global?.entities ?? 0}
        />
        <StatCard
          icon={Brain}
          label="Alta amenaza"
          value={overview?.global?.high_threat ?? 0}
          accent="danger"
        />
        <StatCard
          icon={GitBranch}
          label="Cross-platform"
          value={overview?.global?.cross_platform ?? 0}
        />
        <StatCard
          icon={Radar}
          label="Coord. score"
          value={
            displayGraph
              ? `${(displayGraph.coordination_score * 100).toFixed(0)}%`
              : "—"
          }
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <EngagementHealthPanel metrics={displayEngagement} />
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
                Correlation Graph
              </h2>
              {liveStream && (
                <span className="text-xs text-cyber-muted">
                  {liveStream.channel_name} · {liveStream.platform}
                </span>
              )}
            </div>
            <ThreatGraphCytoscape graph={displayGraph} height={400} />
            {displayGraph && displayGraph.bot_clusters.length > 0 && (
              <p className="text-xs text-cyber-danger mt-2">
                {displayGraph.bot_clusters.length} cluster(s) bot detectados (≥3 nodos)
              </p>
            )}
          </div>
        </div>
        <ThreatIntelLiveFeed topEntities={topEntities} liveAssessment={liveAssessment} />
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  accent?: "danger";
}) {
  return (
    <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 p-4">
      <Icon
        size={20}
        className={cn(
          "mb-2",
          accent === "danger" ? "text-cyber-danger" : "text-cyber-accent",
        )}
      />
      <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      <p className="text-[10px] uppercase text-cyber-muted tracking-wider">{label}</p>
    </div>
  );
}
