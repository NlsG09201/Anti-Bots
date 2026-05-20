"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ChevronRight,
  Globe,
  Loader2,
  Search,
  ShieldAlert,
  Skull,
  Wifi,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { ThreatIntelPanel } from "@/components/ThreatIntelPanel";
import { api, type SuspiciousIP, type ThreatIntelReport } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

function riskClass(score: number): string {
  if (score >= 75) return "text-cyber-danger";
  if (score >= 50) return "text-orange-400";
  if (score >= 25) return "text-yellow-400";
  return "text-cyber-accent";
}

function ThreatCell({ active }: { active: boolean }) {
  return (
    <span className={active ? "text-cyber-danger font-semibold" : "text-cyber-muted/50"}>
      {active ? "✓" : "—"}
    </span>
  );
}

export default function IPsPage() {
  const { accessToken } = useAuthStore();
  const queryClient = useQueryClient();
  const [selectedIp, setSelectedIp] = useState<string | null>(null);
  const [lookupIp, setLookupIp] = useState("");
  const [detail, setDetail] = useState<ThreatIntelReport | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const { data: ips = [], isLoading: listLoading } = useQuery({
    queryKey: ["suspicious-ips"],
    queryFn: () => api.ips.list(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 60000,
  });

  const analyzeMutation = useMutation({
    mutationFn: ({ ip, force }: { ip: string; force?: boolean }) =>
      api.ips.analyze(accessToken!, ip, force),
    onSuccess: (report) => {
      setDetail(report);
      setDetailError(null);
      setSelectedIp(report.ip_address);
      void queryClient.invalidateQueries({ queryKey: ["suspicious-ips"] });
    },
    onError: (err: Error) => {
      setDetailError(err.message || "No se pudo analizar la IP");
    },
  });

  const stats = useMemo(() => {
    const highRisk = ips.filter((ip) => ip.risk_score >= 70).length;
    const proxy = ips.filter(
      (ip) => ip.is_proxy || ip.is_vpn || ip.is_tor || ip.is_residential_proxy,
    ).length;
    const botnet = ips.filter((ip) => ip.is_botnet).length;
    const blocked = ips.filter((ip) => ip.is_blocked).length;
    return { total: ips.length, highRisk, proxy, botnet, blocked };
  }, [ips]);

  const openDetail = (ip: string, force = false) => {
    setSelectedIp(ip);
    setDetail(null);
    setDetailError(null);
    analyzeMutation.mutate({ ip, force });
  };

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = lookupIp.trim();
    if (!trimmed) return;
    openDetail(trimmed);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Globe className="text-cyber-accent" />
            Suspicious IPs
          </h1>
          <p className="text-sm text-cyber-muted mt-1">
            Threat intelligence: VPN, proxy, TOR, datacenter, residential proxy y botnets
          </p>
        </div>
        <form onSubmit={handleLookup} className="flex gap-2 w-full lg:max-w-md">
          <input
            type="text"
            value={lookupIp}
            onChange={(e) => setLookupIp(e.target.value)}
            placeholder="Buscar IP (ej. 203.0.113.1)"
            className="cyber-input text-sm font-mono flex-1"
          />
          <button
            type="submit"
            disabled={analyzeMutation.isPending || !lookupIp.trim()}
            className="cyber-btn-primary flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {analyzeMutation.isPending ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Search size={18} />
            )}
            Analizar
          </button>
        </form>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="IPs sospechosas" value={stats.total} icon={Globe} />
        <StatCard
          title="Alto riesgo"
          value={stats.highRisk}
          icon={ShieldAlert}
          variant={stats.highRisk > 0 ? "danger" : "default"}
        />
        <StatCard
          title="Proxy / VPN / TOR"
          value={stats.proxy}
          icon={Wifi}
          variant={stats.proxy > 0 ? "warning" : "default"}
        />
        <StatCard
          title="Botnet / bloqueadas"
          value={`${stats.botnet} / ${stats.blocked}`}
          icon={Skull}
          variant={stats.botnet > 0 ? "danger" : "default"}
        />
      </div>

      <div className="grid xl:grid-cols-5 gap-6">
        <div className="xl:col-span-3 cyber-card overflow-x-auto p-0">
          {listLoading ? (
            <p className="p-8 text-center text-cyber-muted flex items-center justify-center gap-2">
              <Loader2 className="animate-spin" size={18} />
              Cargando IPs…
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-cyber-muted border-b border-cyber-border">
                  <th className="text-left py-3 px-4" />
                  <th className="text-left py-3 px-2">IP</th>
                  <th className="text-left py-3 px-2">País</th>
                  <th className="text-right py-3 px-2">Risk</th>
                  <th className="text-center py-3 px-1">VPN</th>
                  <th className="text-center py-3 px-1">Px</th>
                  <th className="text-center py-3 px-1">TOR</th>
                  <th className="text-center py-3 px-1">DC</th>
                  <th className="text-center py-3 px-1">Res</th>
                  <th className="text-center py-3 px-1">Bot</th>
                </tr>
              </thead>
              <tbody>
                {ips.map((ip: SuspiciousIP) => {
                  const selected = selectedIp === ip.ip_address;
                  return (
                    <tr
                      key={ip.ip_address}
                      onClick={() => openDetail(ip.ip_address)}
                      className={clsx(
                        "border-b border-cyber-border/50 cursor-pointer transition-colors",
                        selected
                          ? "bg-cyber-accent/10 hover:bg-cyber-accent/15"
                          : "hover:bg-cyber-bg/40",
                      )}
                    >
                      <td className="py-3 pl-4 text-cyber-muted">
                        <ChevronRight
                          size={16}
                          className={clsx(selected && "text-cyber-accent")}
                        />
                      </td>
                      <td className="py-3 px-2 font-mono text-white">{ip.ip_address}</td>
                      <td className="py-3 px-2 text-cyber-muted">{ip.country_code || "—"}</td>
                      <td
                        className={clsx(
                          "py-3 px-2 text-right font-mono font-semibold",
                          riskClass(ip.risk_score),
                        )}
                      >
                        {ip.risk_score.toFixed(0)}
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_vpn} />
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_proxy} />
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_tor} />
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_datacenter} />
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_residential_proxy} />
                      </td>
                      <td className="py-3 px-1 text-center">
                        <ThreatCell active={ip.is_botnet} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {!listLoading && !ips.length && (
            <p className="text-center py-8 text-cyber-muted">
              No hay IPs sospechosas. Usa el buscador para analizar una dirección.
            </p>
          )}
        </div>

        <div className="xl:col-span-2 cyber-card min-h-[320px]">
          <h2 className="text-sm font-semibold text-cyber-muted uppercase tracking-wide mb-4">
            Detalle threat intelligence
          </h2>
          <ThreatIntelPanel
            report={detail}
            loading={analyzeMutation.isPending}
            error={detailError}
            onRefresh={
              selectedIp
                ? () => openDetail(selectedIp, true)
                : undefined
            }
          />
          {detail && detail.flags.length > 0 && (
            <p className="text-xs text-cyber-muted mt-4 border-t border-cyber-border pt-3">
              Fuentes: {detail.sources.join(", ") || "local"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
