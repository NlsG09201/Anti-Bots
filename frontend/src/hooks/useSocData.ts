"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type Alert,
  type Attack,
  type DashboardCharts,
  type DashboardStats,
  type SecurityDashboard,
  type SuspiciousIP,
} from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useWebSocketContext } from "@/contexts/WebSocketContext";
import { COUNTRY_COORDS } from "@/lib/country-coords";

export interface TimelineEntry {
  id: string;
  time: string;
  title: string;
  detail: string;
  severity: "critical" | "high" | "medium" | "low";
  kind: "attack" | "alert" | "event" | "signal";
}

export interface MapThreat {
  id: string;
  countryCode: string;
  label: string;
  lat: number;
  lng: number;
  risk: number;
  ip?: string;
}

export function useSocData() {
  const { accessToken } = useAuthStore();
  const queryClient = useQueryClient();
  const [liveStats, setLiveStats] = useState<DashboardStats | null>(null);
  const [liveCharts, setLiveCharts] = useState<DashboardCharts | null>(null);
  const [liveAlerts, setLiveAlerts] = useState<Alert[]>([]);
  const [liveEvents, setLiveEvents] = useState<
    { time: string; label: string; risk: number }[]
  >([]);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type === "alert" && msg.data) {
        setLiveAlerts((prev) => [msg.data as unknown as Alert, ...prev].slice(0, 30));
        queryClient.invalidateQueries({ queryKey: ["alerts"] });
      }
      if (msg.type === "attack_detected") {
        queryClient.invalidateQueries({ queryKey: ["attacks"] });
      }
      if (msg.type === "stats_update" && msg.data) {
        const d = msg.data;
        const chartsPayload = d.charts as DashboardCharts | undefined;
        setLiveStats({
          active_attacks: Number(d.active_attacks ?? 0),
          total_alerts: Number(d.total_alerts ?? 0),
          blocked_ips: Number(d.blocked_ips ?? 0),
          suspected_bots: Number(d.suspected_bots ?? 0),
          live_viewers: Number(d.live_viewers ?? 0),
          risk_score_avg: Number(d.risk_score_avg ?? 0),
          attacks_last_24h: Number(d.attacks_last_24h ?? 0),
          mitigations_applied: Number(d.mitigations_applied ?? 0),
        });
        if (chartsPayload?.timeline) setLiveCharts(chartsPayload);
      }
      if (msg.type === "stream_event" || msg.type === "suspicious_event") {
        const d = msg.data || {};
        setLiveEvents((prev) =>
          [
            {
              time: new Date().toLocaleTimeString(),
              label: String(d.event_type || msg.type),
              risk: Number(d.risk_score ?? 0),
            },
            ...prev,
          ].slice(0, 40),
        );
      }
    },
    [queryClient],
  );

  const { connected } = useWebSocketContext();
  useWebSocket(onWsMessage);

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.dashboard.stats(accessToken!),
    enabled: !!accessToken,
  });

  const { data: charts } = useQuery({
    queryKey: ["dashboard-charts"],
    queryFn: () => api.dashboard.charts(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 10000,
  });

  const { data: security } = useQuery({
    queryKey: ["security-dashboard", 24],
    queryFn: () => api.security.dashboard(accessToken!, { hours: 24 }),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const { data: alerts = [] } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts.list(accessToken!),
    enabled: !!accessToken,
  });

  const { data: attacks = [] } = useQuery({
    queryKey: ["attacks"],
    queryFn: () => api.attacks.list(accessToken!, "active"),
    enabled: !!accessToken,
  });

  const { data: ips = [] } = useQuery({
    queryKey: ["suspicious-ips"],
    queryFn: () => api.ips.list(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!),
    enabled: !!accessToken,
  });

  const liveStream = useMemo(
    () => streams.find((s) => s.is_live) ?? streams[0],
    [streams],
  );

  const { data: suspectedViewers = [] } = useQuery({
    queryKey: ["viewers-suspected", liveStream?.id],
    queryFn: () => api.streams.viewers(accessToken!, liveStream!.id, "suspected"),
    enabled: !!accessToken && !!liveStream?.id,
    refetchInterval: 15000,
  });

  const displayStats = liveStats ?? stats;
  const timeline = liveCharts?.timeline ?? charts?.timeline ?? [];
  const heatmap = liveCharts?.heatmap ?? charts?.heatmap ?? [];
  const displayAlerts = liveAlerts.length > 0 ? liveAlerts : alerts;

  const mapThreats: MapThreat[] = useMemo(() => {
    const points: MapThreat[] = [];
    const add = (code: string | null | undefined, risk: number, ip?: string, id?: string) => {
      if (!code) return;
      const c = COUNTRY_COORDS[code.toUpperCase()];
      if (!c) return;
      points.push({
        id: id || `${code}-${ip || points.length}`,
        countryCode: code.toUpperCase(),
        label: c.label,
        lat: c.lat,
        lng: c.lng,
        risk,
        ip,
      });
    };
    ips.slice(0, 25).forEach((ip) => add(ip.country_code, ip.risk_score, ip.ip_address));
    security?.recent_signals?.forEach((s, i) => {
      const code = s.flags?.find((f) => f.length === 2)?.toUpperCase();
      add(code || "US", s.risk_score, s.ip_address, `sig-${i}`);
    });
    return points;
  }, [ips, security]);

  const threatTimeline: TimelineEntry[] = useMemo(() => {
    const entries: TimelineEntry[] = [];
    attacks.slice(0, 6).forEach((a) => {
      entries.push({
        id: `atk-${a.id}`,
        time: new Date(a.created_at).toLocaleTimeString(),
        title: a.attack_type.replace(/_/g, " "),
        detail: `Risk ${a.risk_score.toFixed(0)} · ${a.source_ips.length} IPs`,
        severity:
          a.risk_score >= 80 ? "critical" : a.risk_score >= 60 ? "high" : "medium",
        kind: "attack",
      });
    });
    displayAlerts.slice(0, 6).forEach((a) => {
      entries.push({
        id: `alt-${a.id}`,
        time: new Date(a.created_at).toLocaleTimeString(),
        title: a.title,
        detail: a.message,
        severity:
          a.severity === "critical"
            ? "critical"
            : a.severity === "high"
              ? "high"
              : "medium",
        kind: "alert",
      });
    });
    security?.timeline?.slice(-8).forEach((t, i) => {
      entries.push({
        id: `sec-${i}`,
        time: t.time,
        title: "Security events",
        detail: `${t.events} events · ${t.high_risk} high risk`,
        severity: t.high_risk > 5 ? "high" : "low",
        kind: "event",
      });
    });
    liveEvents.slice(0, 5).forEach((e, i) => {
      entries.push({
        id: `live-${i}`,
        time: e.time,
        title: e.label,
        detail: `Risk ${e.risk}`,
        severity: e.risk >= 70 ? "critical" : "medium",
        kind: "signal",
      });
    });
    return entries.slice(0, 16);
  }, [attacks, displayAlerts, security, liveEvents]);

  const gatewayTimeline = useMemo(() => {
    const sec = security?.gateway?.timeline ?? [];
    const events = security?.timeline ?? [];
    if (sec.length) return sec.map((p) => ({ time: p.time, value: p.blocks, label: "Blocks" }));
    return events.map((p) => ({
      time: p.time,
      value: p.events,
      label: "Events",
    }));
  }, [security]);

  return {
    displayStats,
    timeline,
    heatmap,
    gatewayTimeline,
    displayAlerts,
    attacks,
    ips,
    streams,
    liveStream,
    suspectedViewers,
    security: security as SecurityDashboard | undefined,
    mapThreats,
    threatTimeline,
    liveEvents,
    connected,
  };
}
