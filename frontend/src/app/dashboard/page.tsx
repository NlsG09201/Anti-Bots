"use client";

import { Activity, Shield } from "lucide-react";
import { AttackMap } from "@/components/soc/AttackMap";
import { MetricsGrid } from "@/components/soc/MetricsGrid";
import { RealtimeCharts } from "@/components/soc/RealtimeCharts";
import { SuspiciousViewers } from "@/components/soc/SuspiciousViewers";
import { ThreatTimeline } from "@/components/soc/ThreatTimeline";
import { AlertsPanel } from "@/components/soc/AlertsPanel";
import { AdminPanel } from "@/components/soc/AdminPanel";
import { LiveEventFeed } from "@/components/soc/LiveEventFeed";
import { PlatformSocPanel } from "@/components/soc/PlatformSocPanel";
import { KnownBotsPanel } from "@/components/soc/KnownBotsPanel";
import { Badge } from "@/components/ui/badge";
import { useSocData } from "@/hooks/useSocData";
import { useTwitchBotsSoc } from "@/hooks/useTwitchBotsSoc";
import { cn } from "@/lib/utils";

export default function SocDashboardPage() {
  const {
    displayStats,
    timeline,
    heatmap,
    gatewayTimeline,
    displayAlerts,
    suspectedViewers,
    liveStream,
    security,
    mapThreats,
    threatTimeline,
    connected,
    displaySoc,
    socFeedEvents,
    liveEvents,
  } = useSocData();
  const { overview: tbiOverview, detections: tbiDetections, loading: tbiLoading } =
    useTwitchBotsSoc();

  return (
    <div className="space-y-6 -m-2">
      <div className="relative overflow-hidden rounded-2xl border border-cyber-accent/20 bg-gradient-to-r from-cyber-surface via-cyber-bg to-cyber-surface p-6 md:p-8">
        <div className="absolute inset-0 scan-line pointer-events-none opacity-30" />
        <div className="absolute top-0 right-0 w-64 h-64 bg-cyber-accent/5 rounded-full blur-3xl" />
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="text-cyber-accent" size={28} />
              <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
                SOC Command Center
              </h1>
            </div>
            <p className="text-cyber-muted text-sm max-w-xl">
              Monitoreo SOC en tiempo real: Kick, YouTube Live y TikTok Live. Deteccion de bots,
              raids, followbotting y spam con WebSocket y analisis IA.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={connected ? "default" : "muted"}>
              <span
                className={cn(
                  "inline-block w-2 h-2 rounded-full mr-1.5",
                  connected ? "bg-cyber-accent animate-pulse" : "bg-cyber-muted",
                )}
              />
              {connected ? "Live feed" : "Reconnecting"}
            </Badge>
            <Badge variant="info">
              <Activity size={12} className="mr-1 inline" />
              {displayStats?.active_attacks ?? 0} ataques activos
            </Badge>
          </div>
        </div>
      </div>

      <MetricsGrid stats={displayStats} security={security} />

      <PlatformSocPanel soc={displaySoc} />

      <KnownBotsPanel
        overview={tbiOverview}
        detections={tbiDetections}
        loading={tbiLoading}
      />

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-8 space-y-6">
          <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4 backdrop-blur-sm">
            <p className="text-xs uppercase tracking-widest text-cyber-muted mb-3 px-1">
              Mapa global de amenazas
            </p>
            <AttackMap threats={mapThreats} />
          </div>
          <RealtimeCharts
            timeline={timeline}
            heatmap={heatmap}
            gateway={gatewayTimeline}
          />
        </div>
        <div className="xl:col-span-4 space-y-6">
          <SuspiciousViewers viewers={suspectedViewers} stream={liveStream} />
          <ThreatTimeline entries={threatTimeline} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <LiveEventFeed events={socFeedEvents} liveEvents={liveEvents} />
          <AlertsPanel alerts={displayAlerts} />
        </div>
        <AdminPanel security={security} />
      </div>
    </div>
  );
}
