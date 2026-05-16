"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { formatDistanceToNow } from "date-fns";

export default function BansPage() {
  const { accessToken } = useAuthStore();
  const { data: bans = [] } = useQuery({
    queryKey: ["bans"],
    queryFn: () => api.bans.list(accessToken!),
    enabled: !!accessToken,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Active Bans</h1>
      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3">Target</th>
              <th className="text-left py-3">Type</th>
              <th className="text-left py-3">Ban Type</th>
              <th className="text-left py-3">Reason</th>
              <th className="text-center py-3">Auto</th>
              <th className="text-right py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {bans.map((ban) => (
              <tr key={ban.id} className="border-b border-cyber-border/50">
                <td className="py-3 font-mono text-white">{ban.target_value}</td>
                <td className="py-3 text-cyber-muted">{ban.target_type}</td>
                <td className="py-3 capitalize">{ban.ban_type}</td>
                <td className="py-3 text-cyber-muted max-w-xs truncate">{ban.reason}</td>
                <td className="py-3 text-center">{ban.is_automated ? "🤖" : "👤"}</td>
                <td className="py-3 text-right text-cyber-muted">
                  {formatDistanceToNow(new Date(ban.created_at), { addSuffix: true })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!bans.length && <p className="text-center py-8 text-cyber-muted">No active bans</p>}
      </div>
    </div>
  );
}
