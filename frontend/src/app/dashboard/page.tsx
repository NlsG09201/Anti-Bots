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
import { PlatformMonitorHealthPanel } from "@/components/soc/PlatformMonitorHealthPanel";
import { Badge } from "@/components/ui/badge";
import { useSocData } from "@/hooks/useSocData";
import { useTwitchBotsSoc } from "@/hooks/useTwitchBotsSoc";
import { usePlatformMonitorHealth } from "@/hooks/usePlatformMonitorHealth";
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
  const { overview: pmhOverview, loading: pmhLoading } = usePlatformMonitorHealth();

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-cyber-border bg-cyber-surface p-5 sm:p-7">
        <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-cyber-accent/5 blur-3xl" />
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-cyber-accent">
              <Shield size={15} /> Security overview
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-cyber-text md:text-3xl">
              Your live security workspace
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-cyber-muted">
              Review channel activity, threat signals, and moderation alerts. Metrics reflect the data available from your connected channels.
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

      <PlatformMonitorHealthPanel overview={pmhOverview} loading={pmhLoading} />

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
