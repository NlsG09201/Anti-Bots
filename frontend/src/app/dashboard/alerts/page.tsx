"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { LiveAlerts } from "@/components/LiveAlerts";

export default function AlertsPage() {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();

  const { data: alerts = [] } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts.list(accessToken!),
    enabled: !!accessToken,
  });

  const acknowledge = useMutation({
    mutationFn: (id: string) => api.alerts.acknowledge(accessToken!, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Security Alerts</h1>
      <LiveAlerts
        alerts={alerts}
        onAcknowledge={(id) => acknowledge.mutate(id)}
      />
    </div>
  );
}
