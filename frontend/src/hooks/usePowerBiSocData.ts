"use client";

import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PowerBiSyncResult } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function usePowerBiSocData(hours = 168) {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();

  const invalidateAnalytics = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["power-bi-analytics"] });
  }, [queryClient]);

  useWebSocket(
    useCallback(
      (msg) => {
        if (
          msg.type === "soc_update" ||
          msg.type === "live_intel_update" ||
          msg.type === "attack_detected" ||
          msg.type === "viewer_flow_update"
        ) {
          invalidateAnalytics();
        }
      },
      [invalidateAnalytics],
    ),
  );

  const overview = useQuery({
    queryKey: ["power-bi-analytics", "overview", hours],
    queryFn: () => api.powerBiAnalytics.overview(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 15000,
  });

  const live = useQuery({
    queryKey: ["power-bi-analytics", "live", hours],
    queryFn: () => api.powerBiAnalytics.liveMetrics(accessToken!, Math.min(hours, 168)),
    enabled: !!accessToken,
    refetchInterval: 10000,
  });

  const streams = useQuery({
    queryKey: ["power-bi-analytics", "streams", hours],
    queryFn: () => api.powerBiAnalytics.streamAnalytics(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const attacks = useQuery({
    queryKey: ["power-bi-analytics", "attacks", hours],
    queryFn: () => api.powerBiAnalytics.attackAnalytics(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const ai = useQuery({
    queryKey: ["power-bi-analytics", "ai", hours],
    queryFn: () => api.powerBiAnalytics.aiAnalytics(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const engagement = useQuery({
    queryKey: ["power-bi-analytics", "engagement", hours],
    queryFn: () => api.powerBiAnalytics.engagementAnalytics(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const suspicious = useQuery({
    queryKey: ["power-bi-analytics", "suspicious", hours],
    queryFn: () => api.powerBiAnalytics.suspiciousActivity(accessToken!, Math.min(hours, 720)),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const metadata = useQuery({
    queryKey: ["power-bi-analytics", "metadata", hours],
    queryFn: () => api.powerBiAnalytics.metadata(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 60000,
  });

  const executive = useQuery({
    queryKey: ["power-bi-analytics", "executive", hours],
    queryFn: () => api.powerBiAnalytics.executiveReport(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 60000,
  });

  const sync = useMutation<PowerBiSyncResult>({
    mutationFn: () => api.powerBiAnalytics.sync(accessToken!, hours),
    onSuccess: invalidateAnalytics,
  });

  const loading =
    overview.isLoading ||
    live.isLoading ||
    streams.isLoading ||
    attacks.isLoading ||
    ai.isLoading ||
    engagement.isLoading ||
    suspicious.isLoading ||
    metadata.isLoading ||
    executive.isLoading;

  const error =
    overview.error ||
    live.error ||
    streams.error ||
    attacks.error ||
    ai.error ||
    engagement.error ||
    suspicious.error ||
    metadata.error ||
    executive.error;

  return {
    accessToken,
    overview: overview.data,
    live: live.data,
    streams: streams.data,
    attacks: attacks.data,
    ai: ai.data,
    engagement: engagement.data,
    suspicious: suspicious.data,
    metadata: metadata.data,
    executive: executive.data,
    loading,
    error,
    sync,
    refresh: invalidateAnalytics,
  };
}
