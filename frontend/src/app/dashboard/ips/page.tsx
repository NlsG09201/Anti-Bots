"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

export default function IPsPage() {
  const { accessToken } = useAuthStore();
  const { data: ips = [] } = useQuery({
    queryKey: ["suspicious-ips"],
    queryFn: () => api.ips.list(accessToken!),
    enabled: !!accessToken,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Suspicious IPs</h1>
      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3">IP Address</th>
              <th className="text-left py-3">Country</th>
              <th className="text-right py-3">Reputation</th>
              <th className="text-center py-3">Proxy</th>
              <th className="text-center py-3">VPN</th>
              <th className="text-center py-3">TOR</th>
              <th className="text-center py-3">DC</th>
              <th className="text-center py-3">Blocked</th>
            </tr>
          </thead>
          <tbody>
            {ips.map((ip) => (
              <tr key={ip.ip_address} className="border-b border-cyber-border/50 hover:bg-cyber-bg/30">
                <td className="py-3 font-mono text-white">{ip.ip_address}</td>
                <td className="py-3 text-cyber-muted">{ip.country_code || "—"}</td>
                <td className="py-3 text-right font-mono text-cyber-danger">{ip.reputation_score.toFixed(0)}</td>
                <td className="py-3 text-center">{ip.is_proxy ? "✓" : "—"}</td>
                <td className="py-3 text-center">{ip.is_vpn ? "✓" : "—"}</td>
                <td className="py-3 text-center">{ip.is_tor ? "✓" : "—"}</td>
                <td className="py-3 text-center">{ip.is_datacenter ? "✓" : "—"}</td>
                <td className="py-3 text-center">{ip.is_blocked ? "🚫" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!ips.length && <p className="text-center py-8 text-cyber-muted">No suspicious IPs detected</p>}
      </div>
    </div>
  );
}
