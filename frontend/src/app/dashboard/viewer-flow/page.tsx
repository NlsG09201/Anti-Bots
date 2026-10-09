"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ViewerFlowDashboard } from "@/components/viewer-flow/ViewerFlowDashboard";
import { useViewerFlow } from "@/hooks/useViewerFlow";
import { useSocData } from "@/hooks/useSocData";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

export default function ViewerFlowPage() {
  const accessToken = useApiToken();
  const { liveStream } = useSocData();
  const streamId = liveStream?.id;

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!, true),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const nonTwitchLive = useMemo(
    () =>
      streams.filter(
        (s) =>
          s.is_live &&
          ["kick", "youtube", "tiktok"].includes((s.platform || "").toLowerCase()),
      ),
    [streams],
  );

  const activeStream =
    nonTwitchLive.find((s) => s.id === streamId) ?? nonTwitchLive[0];

  const { overview, streamSnap, loading, scan } = useViewerFlow(activeStream?.id);

  return (
    <ViewerFlowDashboard
      overview={overview}
      streamSnap={streamSnap}
      loading={loading}
      streamId={activeStream?.id}
      onScan={
        activeStream?.id
          ? () => {
              void scan(activeStream.id);
            }
          : undefined
      }
    />
  );
}
