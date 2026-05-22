"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type TwitchBotsDetection, type TwitchBotsOverview } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";

export function useTwitchBotsSoc() {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const [liveDetections, setLiveDetections] = useState<TwitchBotsDetection[]>([]);

  const onWsMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      if (msg.type !== "twitchbots_detection" || !msg.data) return;
      const d = msg.data;
      setLiveDetections((prev) =>
        [
          {
            username: String(d.username || ""),
            twitch_id: d.twitch_id ? String(d.twitch_id) : undefined,
            bot_type: d.bot_type ? String(d.bot_type) : undefined,
            threat_level: (d.threat_level as TwitchBotsDetection["threat_level"]) || "high",
            suspicious_score: Number(d.suspicious_score ?? 0),
            stream_id: d.stream_id ? String(d.stream_id) : undefined,
            detected_at: new Date().toISOString(),
          },
          ...prev,
        ].slice(0, 30),
      );
      queryClient.invalidateQueries({ queryKey: ["twitchbots-overview"] });
    },
    [queryClient],
  );

  useWebSocket(onWsMessage);

  const overviewQuery = useQuery({
    queryKey: ["twitchbots-overview"],
    queryFn: () => api.twitchbots.overview(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 20000,
  });

  const detectionsQuery = useQuery({
    queryKey: ["twitchbots-detections"],
    queryFn: () => api.twitchbots.detections(accessToken!, 40),
    enabled: !!accessToken,
    refetchInterval: 25000,
  });

  const overview: TwitchBotsOverview | undefined = overviewQuery.data;
  const detections =
    liveDetections.length > 0
      ? liveDetections
      : (detectionsQuery.data?.detections ?? []);

  return {
    enabled: overview?.enabled ?? true,
    overview,
    detections,
    loading: overviewQuery.isLoading,
  };
}
