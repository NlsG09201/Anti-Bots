"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Attack } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import clsx from "clsx";
import { Shield } from "lucide-react";

function AttacksContent() {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const streamId = searchParams.get("stream") ?? undefined;
  const [message, setMessage] = useState("");

  const { data: attacks = [], isLoading } = useQuery({
    queryKey: ["attacks-all", streamId],
    queryFn: () => api.attacks.list(accessToken!, undefined, streamId),
    enabled: !!accessToken,
  });

  const mitigate = useMutation({
    mutationFn: ({ attack, full }: { attack: Attack; full: boolean }) => {
      if (full) {
        return api.attacks.mitigate(accessToken!, attack.id, { full_mitigation: true });
      }
      const suspected = (attack.evidence?.suspected_usernames as string[] | undefined) ?? [];
      const proxyIps = (attack.evidence?.proxy_ips as string[] | undefined) ?? [];
      const targets = [
        ...attack.source_ips
          .filter((ip) => ip?.trim())
          .slice(0, 10)
          .map((ip) => ({ type: "ip" as const, value: ip.trim() })),
        ...proxyIps
          .filter((ip) => ip?.trim())
          .slice(0, 10)
          .map((ip) => ({ type: "ip" as const, value: String(ip).trim() })),
        ...suspected
          .filter((u) => u?.trim())
          .slice(0, 10)
          .map((u) => ({ type: "user_login" as const, value: String(u).trim() })),
      ];
      return api.attacks.mitigate(accessToken!, attack.id, { targets });
    },
    onSuccess: (res: {
      bans_created?: number;
      targets?: number;
      full_mitigation?: boolean;
      acknowledge_only?: boolean;
      message?: string | null;
    }) => {
      if (res.message) {
        setMessage(res.message);
      } else if (res.acknowledge_only) {
        setMessage(
          `Ataque cerrado (modo observación): ${res.bans_created ?? 0} bans locales, sin objetivos en plataforma.`,
        );
      } else {
        setMessage(
          `Mitigado: ${res.bans_created ?? 0} bans · ${res.targets ?? 0} objetivos${res.full_mitigation ? " (mitigación completa)" : ""}`,
        );
      }
      queryClient.invalidateQueries({ queryKey: ["attacks-all"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Monitor de ataques</h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-2xl">
          Mitigacion completa bloquea usuarios sospechosos, IPs de proxy/VPN y fingerprints
          detectados en el ataque y en eventos recientes del canal.
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyber-accent border border-cyber-accent/30 rounded-lg px-4 py-2">
          {message}
        </p>
      )}

      {streamId && (
        <p className="text-sm text-cyber-muted">
          Filtrado por canal ·{" "}
          <a href="/dashboard/attacks" className="text-cyber-accent hover:underline">
            ver todos
          </a>
        </p>
      )}

      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3 px-2">Tipo</th>
              <th className="text-left py-3 px-2">Severidad</th>
              <th className="text-left py-3 px-2">Estado</th>
              <th className="text-right py-3 px-2">Risk</th>
              <th className="text-left py-3 px-2">IPs proxy</th>
              <th className="text-left py-3 px-2">IA</th>
              <th className="text-right py-3 px-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {attacks.map((attack) => {
              const proxyIps = [
                ...(attack.source_ips || []),
                ...((attack.evidence?.proxy_ips as string[]) || []),
              ].filter(Boolean);
              const suspected = (attack.evidence?.suspected_usernames as string[]) || [];
              return (
                <tr key={attack.id} className="border-b border-cyber-border/50 hover:bg-cyber-bg/30">
                  <td className="py-3 px-2 text-white capitalize">
                    {attack.attack_type.replace("_", " ")}
                  </td>
                  <td className="py-3 px-2">
                    <span className={clsx("text-xs px-2 py-0.5 rounded", `severity-${attack.severity}`)}>
                      {attack.severity}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-cyber-muted">{attack.status}</td>
                  <td className="py-3 px-2 text-right font-mono text-cyber-danger">
                    {attack.risk_score.toFixed(1)}
                  </td>
                  <td className="py-3 px-2 text-xs text-cyber-muted max-w-[120px] truncate" title={proxyIps.join(", ")}>
                    {proxyIps.length ? `${proxyIps.length} IP(s)` : "—"}
                    {suspected.length > 0 && ` · ${suspected.length} user(s)`}
                  </td>
                  <td className="py-3 px-2 text-xs text-cyber-muted max-w-[200px] truncate">
                    {(attack.evidence?.ai_insight as { summary?: string })?.summary?.slice(0, 60) ?? "—"}
                  </td>
                  <td className="py-3 px-2 text-right space-x-2">
                    {attack.status === "active" && (
                      <>
                        <button
                          onClick={() => mitigate.mutate({ attack, full: false })}
                          disabled={mitigate.isPending}
                          className="text-xs px-2 py-1 rounded border border-cyber-border text-cyber-muted hover:text-white"
                        >
                          Mitigar
                        </button>
                        <button
                          onClick={() => mitigate.mutate({ attack, full: true })}
                          disabled={mitigate.isPending}
                          className="inline-flex items-center gap-1 cyber-btn-danger text-xs px-2 py-1"
                        >
                          <Shield size={12} /> Completo
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {isLoading && <p className="text-center py-8 text-cyber-muted">Cargando...</p>}
        {!isLoading && !attacks.length && (
          <p className="text-center py-8 text-cyber-muted">Sin ataques registrados</p>
        )}
      </div>
    </div>
  );
}

export default function AttacksPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-6">Cargando ataques...</p>}>
      <AttacksContent />
    </Suspense>
  );
}
