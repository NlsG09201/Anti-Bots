"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldAlert,
  Ban,
  Gauge,
  Globe,
  Bot,
  Activity,
  Filter,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { SecurityBlocksChart, SecurityEventsChart } from "@/components/SecurityChart";
import { api, type Stream } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

const HOUR_OPTIONS = [6, 12, 24, 48, 72];

function reasonLabel(reason: string): string {
  const map: Record<string, string> = {
    rate_limit_429: "Rate limit (429)",
    headers_403: "Headers inválidos",
    spoof_403: "IP spoofing",
    automation_403: "Automatización",
    widget_blocked_403: "Widget bloqueado",
    replay_400: "Replay detectado",
    payload_413: "Payload grande",
    query_414: "Query larga",
    scanner_404: "Escaneo bloqueado",
  };
  return map[reason] || reason;
}

export default function SecurityDashboardPage() {
  const { accessToken } = useAuthStore();
  const [hours, setHours] = useState(24);
  const [streamId, setStreamId] = useState("");

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!),
    enabled: !!accessToken,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["security-dashboard", hours, streamId],
    queryFn: () =>
      api.security.dashboard(accessToken!, {
        hours,
        streamId: streamId || undefined,
      }),
    enabled: !!accessToken,
    refetchInterval: 30000,
  });

  const summary = data?.summary;
  const topFlags = data?.top_flags ?? [];
  const topReasons = data?.gateway?.top_reasons ?? [];
  const perStream = data?.per_stream ?? [];
  const recent = data?.recent_signals ?? [];

  const streamOptions = useMemo(
    () =>
      (streams as Stream[]).map((s) => ({
        id: s.id,
        label: s.channel_name || s.id.slice(0, 8),
      })),
    [streams],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ShieldAlert className="text-cyber-accent" />
            Security SOC
          </h1>
          <p className="text-sm text-cyber-muted mt-1">
            Bloqueos 429/403, proxy/VPN, flags y señales por canal
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-cyber-muted">
            <Filter size={16} />
            <select
              value={streamId}
              onChange={(e) => setStreamId(e.target.value)}
              className="cyber-input text-sm min-w-[160px]"
            >
              <option value="">Todos los canales</option>
              {streamOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="cyber-input text-sm"
          >
            {HOUR_OPTIONS.map((h) => (
              <option key={h} value={h}>
                Últimas {h}h
              </option>
            ))}
          </select>
        </div>
      </div>

      {isError && (
        <p className="text-cyber-danger text-sm">
          No se pudieron cargar las métricas de seguridad.
        </p>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Bloqueos 429"
          value={isLoading ? "…" : String(summary?.blocks_429 ?? 0)}
          icon={Gauge}
        />
        <StatCard
          title="Bloqueos 403"
          value={isLoading ? "…" : String(summary?.blocks_403 ?? 0)}
          icon={Ban}
        />
        <StatCard
          title="Proxy / VPN"
          value={
            isLoading
              ? "…"
              : `${summary?.proxy_detections ?? 0} / ${summary?.vpn_detections ?? 0}`
          }
          icon={Globe}
        />
        <StatCard
          title="Automatización"
          value={isLoading ? "…" : String(summary?.automation_signals ?? 0)}
          icon={Bot}
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="cyber-card p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Bloqueos en gateway</h2>
          <SecurityBlocksChart gateway={data?.gateway?.timeline ?? []} />
        </div>
        <div className="cyber-card p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Eventos por hora</h2>
          <SecurityEventsChart events={data?.timeline ?? []} />
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="cyber-card p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Top motivos de bloqueo</h2>
          <ul className="space-y-2">
            {topReasons.length === 0 && (
              <li className="text-cyber-muted text-sm py-4 text-center">
                Sin bloqueos en el periodo
              </li>
            )}
            {topReasons.map((r) => (
              <li
                key={r.reason}
                className="flex justify-between items-center py-2 border-b border-cyber-border/50"
              >
                <span className="text-sm text-cyber-muted">{reasonLabel(r.reason)}</span>
                <span className="font-mono text-cyber-accent">{r.count}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="cyber-card p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Top flags de seguridad</h2>
          <ul className="space-y-2">
            {topFlags.length === 0 && (
              <li className="text-cyber-muted text-sm py-4 text-center">
                Sin flags registrados
              </li>
            )}
            {topFlags.map((f) => (
              <li
                key={f.flag}
                className="flex justify-between items-center py-2 border-b border-cyber-border/50"
              >
                <span className="text-sm text-cyber-muted font-mono truncate max-w-[70%]">
                  {f.flag}
                </span>
                <span className="font-mono text-cyber-danger">{f.count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="cyber-card overflow-x-auto">
        <h2 className="text-sm font-semibold text-white p-4 pb-0 flex items-center gap-2">
          <Activity size={16} className="text-cyber-accent" />
          Por canal
        </h2>
        <table className="w-full text-sm mt-2">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3 px-4">Canal</th>
              <th className="text-right py-3">Eventos</th>
              <th className="text-right py-3">Proxy</th>
              <th className="text-right py-3">VPN</th>
              <th className="text-right py-3 px-4">Alto riesgo</th>
            </tr>
          </thead>
          <tbody>
            {perStream.map((row) => (
              <tr
                key={row.stream_id}
                className="border-b border-cyber-border/50 hover:bg-cyber-bg/30"
              >
                <td className="py-3 px-4 text-white">{row.channel_name}</td>
                <td className="py-3 text-right font-mono">{row.events}</td>
                <td className="py-3 text-right font-mono text-amber-400">{row.proxy}</td>
                <td className="py-3 text-right font-mono text-orange-400">{row.vpn}</td>
                <td className="py-3 px-4 text-right font-mono text-cyber-danger">
                  {row.high_risk}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!perStream.length && !isLoading && (
          <p className="text-center py-8 text-cyber-muted text-sm">
            Sin eventos de seguridad en el periodo seleccionado
          </p>
        )}
      </div>

      <div className="cyber-card p-4">
        <h2 className="text-sm font-semibold text-white mb-3">Señales recientes</h2>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {recent.length === 0 && (
            <p className="text-cyber-muted text-sm text-center py-4">Sin señales recientes</p>
          )}
          {recent.map((sig, i) => (
            <div
              key={`${sig.ip_address}-${i}`}
              className="flex flex-wrap gap-3 items-center justify-between py-2 px-3 rounded-lg bg-cyber-bg/50 border border-cyber-border/40 text-sm"
            >
              <span className="font-mono text-white">{sig.ip_address || "—"}</span>
              <span className="text-cyber-danger font-mono">
                risk{" "}
                {typeof sig.risk_score === "number"
                  ? sig.risk_score.toFixed(0)
                  : sig.risk_score}
              </span>
              {sig.is_proxy && <span className="text-amber-400 text-xs">proxy</span>}
              {sig.is_vpn && <span className="text-orange-400 text-xs">vpn</span>}
              {sig.flags?.length > 0 && (
                <span className="text-cyber-muted text-xs truncate max-w-[40%]">
                  {sig.flags.join(", ")}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
