"use client";

import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

export default function ViewersPage() {
  const { accessToken } = useAuthStore();

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!),
    enabled: !!accessToken,
  });

  const streamId = streams[0]?.id;

  const { data: viewers = [] } = useQuery({
    queryKey: ["viewers", streamId],
    queryFn: () => api.streams.viewers(accessToken!, streamId!),
    enabled: !!accessToken && !!streamId,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-info" />
          Monitor de viewers
        </h1>
        <p className="text-cyber-muted text-sm mt-1">
          {streams[0]?.channel_name
            ? `Canal: ${streams[0].channel_name}`
            : "Conecta Twitch en Settings para ver viewers en vivo"}
        </p>
      </div>

      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3">Usuario</th>
              <th className="text-left py-3">IP</th>
              <th className="text-right py-3">Risk Score</th>
              <th className="text-center py-3">Bot?</th>
              <th className="text-center py-3">Activo</th>
            </tr>
          </thead>
          <tbody>
            {viewers.map((v) => (
              <tr key={v.id} className="border-b border-cyber-border/50 hover:bg-cyber-bg/30">
                <td className="py-3 text-white">{v.platform_username || "—"}</td>
                <td className="py-3 font-mono text-cyber-muted">{v.ip_address}</td>
                <td className="py-3 text-right font-mono text-cyber-danger">
                  {v.risk_score.toFixed(0)}
                </td>
                <td className="py-3 text-center">{v.is_suspected_bot ? "⚠" : "—"}</td>
                <td className="py-3 text-center">{v.is_active ? "●" : "○"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!streamId && (
          <p className="text-center py-12 text-cyber-muted">
            Sin streams conectados — ve a Settings y conecta Twitch
          </p>
        )}
        {streamId && viewers.length === 0 && (
          <p className="text-center py-12 text-cyber-muted">No hay viewers activos</p>
        )}
      </div>
    </div>
  );
}
