"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

export default function FingerprintsPage() {
  const accessToken = useApiToken();
  const { data: fingerprints = [] } = useQuery({
    queryKey: ["fingerprints"],
    queryFn: () => api.fingerprints.list(accessToken!),
    enabled: !!accessToken,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Device Fingerprints</h1>
      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3">Hash</th>
              <th className="text-right py-3">Risk Score</th>
              <th className="text-center py-3">Headless</th>
              <th className="text-right py-3">Occurrences</th>
              <th className="text-left py-3">Flags</th>
              <th className="text-center py-3">Blocked</th>
            </tr>
          </thead>
          <tbody>
            {fingerprints.map((fp) => (
              <tr key={fp.hash} className="border-b border-cyber-border/50">
                <td className="py-3 font-mono text-xs text-white">{fp.hash.slice(0, 16)}...</td>
                <td className="py-3 text-right font-mono text-cyber-danger">{fp.risk_score.toFixed(0)}</td>
                <td className="py-3 text-center">{fp.is_headless ? "⚠" : "—"}</td>
                <td className="py-3 text-right">{fp.occurrence_count}</td>
                <td className="py-3 text-xs text-cyber-muted">{fp.automation_flags.join(", ") || "—"}</td>
                <td className="py-3 text-center">{fp.is_blocked ? "🚫" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
