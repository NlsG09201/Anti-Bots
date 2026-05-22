"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PlatformHealthOverview } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function usePlatformMonitorHealth() {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const [liveOverview, setLiveOverview] = useState<PlatformHealthOverview | null>(null);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type !== "platform_monitor_health" || !msg.data) return;
      setLiveOverview(msg.data as unknown as PlatformHealthOverview);
      queryClient.invalidateQueries({ queryKey: ["platform-health"] });
    },
    [queryClient],
  );

  useWebSocket(onWsMessage);

  const query = useQuery({
    queryKey: ["platform-health"],
    queryFn: () => api.platformHealth.overview(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const overview = liveOverview ?? query.data;

  return {
    overview,
    loading: query.isLoading,
    refetch: query.refetch,
  };
}
