"use client";

import { useCallback, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PowerBiSyncResult } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket, type WSMessage } from "@/hooks/useWebSocket";

export function usePowerBiSocData(hours = 168) {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const invalidateAnalytics = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      void queryClient.invalidateQueries({ queryKey: ["power-bi-analytics"] });
    }, 5000);
  }, [queryClient]);

  useEffect(() => () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
  }, []);

  useWebSocket(
    useCallback(
      (msg: WSMessage) => {
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

  const dashboard = useQuery({
    queryKey: ["power-bi-analytics", "dashboard", hours],
    queryFn: () => api.powerBiAnalytics.dashboardData(accessToken!, hours),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const sync = useMutation<PowerBiSyncResult>({
    mutationFn: () => api.powerBiAnalytics.sync(accessToken!, hours),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["power-bi-analytics"] }),
  });

  return {
    accessToken,
    overview: dashboard.data?.overview,
    live: dashboard.data?.live,
    streams: dashboard.data?.streams,
    attacks: dashboard.data?.attacks,
    ai: dashboard.data?.ai,
    engagement: dashboard.data?.engagement,
    suspicious: dashboard.data?.suspicious,
    metadata: dashboard.data?.metadata,
    executive: dashboard.data?.executive,
    loading: dashboard.isLoading,
    error: dashboard.error,
    sync,
    refresh: dashboard.refetch,
  };
}
