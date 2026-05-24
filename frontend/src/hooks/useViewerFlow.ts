"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type ViewerFlowOverview,
  type ViewerFlowStreamSnapshot,
} from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function useViewerFlow(streamId?: string) {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const [liveMetrics, setLiveMetrics] = useState<Record<string, unknown> | null>(
    null,
  );
  const [liveTimeline, setLiveTimeline] = useState<
    ViewerFlowStreamSnapshot["timeline"]
  >([]);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type !== "viewer_flow_update" || !msg.data) return;
      const sid = String(msg.data.stream_id || "");
      if (streamId && sid !== streamId) return;
      if (msg.data.metrics) {
        setLiveMetrics(msg.data.metrics as Record<string, unknown>);
      }
      if (Array.isArray(msg.data.timeline)) {
        setLiveTimeline(
          msg.data.timeline as ViewerFlowStreamSnapshot["timeline"],
        );
      }
      queryClient.invalidateQueries({ queryKey: ["viewer-flow"] });
    },
    [queryClient, streamId],
  );

  useWebSocket(onWsMessage);

  const overviewQuery = useQuery({
    queryKey: ["viewer-flow", "overview"],
    queryFn: () => api.viewerFlow.overview(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 25000,
  });

  const streamQuery = useQuery({
    queryKey: ["viewer-flow", "stream", streamId],
    queryFn: () => api.viewerFlow.stream(accessToken!, streamId!),
    enabled: !!accessToken && !!streamId,
    refetchInterval: 20000,
  });

  const overview: ViewerFlowOverview | undefined = overviewQuery.data;
  const streamSnap: ViewerFlowStreamSnapshot | undefined = streamQuery.data
    ? {
        metrics: streamQuery.data.metrics,
        timeline: streamQuery.data.timeline,
        suspicious_viewers: streamQuery.data.suspicious_viewers,
        viewer_history: streamQuery.data.viewer_history,
      }
    : undefined;

  const displayMetrics = streamSnap?.metrics
    ? (liveMetrics && streamSnap.metrics.stream_id
        ? ({
            ...streamSnap.metrics,
            ...liveMetrics,
          } as ViewerFlowStreamSnapshot["metrics"])
        : streamSnap.metrics)
    : undefined;

  const displayTimeline =
    liveTimeline.length > 0
      ? [...liveTimeline, ...(streamSnap?.timeline ?? [])].slice(0, 60)
      : streamSnap?.timeline ?? [];

  const finalSnapshot: ViewerFlowStreamSnapshot | undefined = 
    streamSnap && streamSnap.metrics && streamSnap.metrics.stream_id
      ? {
          metrics: displayMetrics!,
          timeline: displayTimeline,
          suspicious_viewers: streamSnap.suspicious_viewers,
          viewer_history: streamSnap.viewer_history,
        }
      : undefined;

  return {
    overview,
    streamSnap: finalSnapshot,
    loading: overviewQuery.isLoading || streamQuery.isLoading,
    scan: async (id: string) => {
      if (!accessToken) return;
      await api.viewerFlow.scan(accessToken, id);
      queryClient.invalidateQueries({ queryKey: ["viewer-flow"] });
    },
  };
}
