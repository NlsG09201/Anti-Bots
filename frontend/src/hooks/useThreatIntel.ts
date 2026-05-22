"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  type EngagementMetrics,
  type ThreatGraphSnapshot,
  type ThreatIntelAssessment,
  type ThreatIntelOverviewResponse,
} from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function useThreatIntel(streamId?: string) {
  const accessToken = useApiToken();
  const [liveAssessment, setLiveAssessment] = useState<ThreatIntelAssessment | null>(null);
  const [liveEngagement, setLiveEngagement] = useState<EngagementMetrics | null>(null);

  const onWsMessage = useCallback((msg: { type: string; data?: Record<string, unknown> }) => {
    if (msg.type !== "threat_intel_update" || !msg.data) return;
    const payload = msg.data.payload as ThreatIntelAssessment | undefined;
    if (!payload) return;
    if (streamId && msg.data.stream_id !== streamId) return;
    setLiveAssessment(payload);
    if (payload.engagement) setLiveEngagement(payload.engagement);
  }, [streamId]);

  useWebSocket(onWsMessage);

  const overview = useQuery({
    queryKey: ["ti-overview"],
    queryFn: () => api.streamingIntelligence.overview(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const engagementQuery = useQuery({
    queryKey: ["ti-engagement", streamId],
    queryFn: () => api.streamingIntelligence.engagement(accessToken!, streamId!),
    enabled: !!accessToken && !!streamId,
    refetchInterval: 12000,
  });

  const graphQuery = useQuery({
    queryKey: ["ti-graph", streamId],
    queryFn: () => api.streamingIntelligence.graph(accessToken!, streamId!),
    enabled: !!accessToken && !!streamId,
    refetchInterval: 15000,
  });

  const topEntities = useQuery({
    queryKey: ["ti-top-entities"],
    queryFn: () => api.streamingIntelligence.topEntities(accessToken!, 30),
    enabled: !!accessToken,
    refetchInterval: 25000,
  });

  const displayEngagement =
    liveEngagement ?? engagementQuery.data?.engagement ?? null;
  const displayGraph: ThreatGraphSnapshot | null =
    liveAssessment?.graph ?? graphQuery.data?.graph ?? null;

  return {
    overview: overview.data as ThreatIntelOverviewResponse | undefined,
    overviewLoading: overview.isLoading,
    displayEngagement,
    displayGraph,
    liveAssessment,
    topEntities: topEntities.data?.entities ?? [],
    graphLoading: graphQuery.isLoading,
  };
}
