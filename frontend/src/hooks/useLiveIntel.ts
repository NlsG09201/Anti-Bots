"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type LiveIntelOverview,
  type LiveStreamSnapshot,
} from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function useLiveIntel() {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const [liveSnapshots, setLiveSnapshots] = useState<LiveStreamSnapshot[]>([]);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type !== "live_intel_update" || !msg.data) return;
      const snaps = msg.data.snapshots as LiveStreamSnapshot[] | undefined;
      if (snaps?.length) setLiveSnapshots(snaps);
      queryClient.invalidateQueries({ queryKey: ["live-intel-overview"] });
    },
    [queryClient],
  );

  useWebSocket(onWsMessage);

  const overviewQuery = useQuery({
    queryKey: ["live-intel-overview"],
    queryFn: () => api.liveIntelligence.overview(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 15000,
  });

  const streamsQuery = useQuery({
    queryKey: ["live-intel-streams"],
    queryFn: () => api.liveIntelligence.streams(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const anomaliesQuery = useQuery({
    queryKey: ["live-intel-anomalies"],
    queryFn: () => api.liveIntelligence.anomalies(accessToken!, 30),
    enabled: !!accessToken,
    refetchInterval: 25000,
  });

  const overview: LiveIntelOverview | undefined = overviewQuery.data?.overview;
  const displaySnapshots =
    liveSnapshots.length > 0 ? liveSnapshots : overview?.snapshots ?? [];

  return {
    enabled: overviewQuery.data?.enabled ?? true,
    overview,
    displaySnapshots,
    streams: streamsQuery.data?.streams ?? [],
    anomalies: anomaliesQuery.data?.anomalies ?? [],
    loading: overviewQuery.isLoading,
  };
}
