"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Attack } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import clsx from "clsx";

export default function AttacksPage() {
  const { accessToken } = useAuthStore();
  const queryClient = useQueryClient();

  const { data: attacks = [], isLoading } = useQuery({
    queryKey: ["attacks-all"],
    queryFn: () => api.attacks.list(accessToken!),
    enabled: !!accessToken,
  });

  const mitigate = useMutation({
    mutationFn: (attack: Attack) =>
      api.attacks.mitigate(accessToken!, attack.id, {
        targets: attack.source_ips.slice(0, 5).map((ip) => ({ type: "ip", value: ip })),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["attacks-all"] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Attack Monitor</h1>

      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3 px-2">Type</th>
              <th className="text-left py-3 px-2">Severity</th>
              <th className="text-left py-3 px-2">Status</th>
              <th className="text-right py-3 px-2">Risk</th>
              <th className="text-right py-3 px-2">Confidence</th>
              <th className="text-left py-3 px-2">Correlation ID</th>
              <th className="text-right py-3 px-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {attacks.map((attack) => (
              <tr key={attack.id} className="border-b border-cyber-border/50 hover:bg-cyber-bg/30">
                <td className="py-3 px-2 text-white capitalize">{attack.attack_type.replace("_", " ")}</td>
                <td className="py-3 px-2">
                  <span className={clsx("text-xs px-2 py-0.5 rounded", `severity-${attack.severity}`)}>
                    {attack.severity}
                  </span>
                </td>
                <td className="py-3 px-2 text-cyber-muted">{attack.status}</td>
                <td className="py-3 px-2 text-right font-mono text-cyber-danger">{attack.risk_score.toFixed(1)}</td>
                <td className="py-3 px-2 text-right font-mono">{(attack.confidence * 100).toFixed(0)}%</td>
                <td className="py-3 px-2 font-mono text-xs text-cyber-muted">{attack.correlation_id.slice(0, 12)}...</td>
                <td className="py-3 px-2 text-right">
                  {attack.status === "active" && (
                    <button
                      onClick={() => mitigate.mutate(attack)}
                      disabled={mitigate.isPending}
                      className="cyber-btn-danger text-xs px-3 py-1"
                    >
                      Mitigate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="text-center py-8 text-cyber-muted">Loading attacks...</p>}
        {!isLoading && !attacks.length && (
          <p className="text-center py-8 text-cyber-muted">No attacks recorded</p>
        )}
      </div>
    </div>
  );
}
