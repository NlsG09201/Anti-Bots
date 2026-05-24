"use client";

import { Activity, Radio, Server, Wifi, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PlatformBadge } from "@/components/PlatformBadge";
import type {
  PlatformHealthOverview,
  PlatformHealthStream,
  IntegrationProbe,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  healthy: "text-cyber-accent border-cyber-accent/40 bg-cyber-accent/10",
  degraded: "text-yellow-300 border-yellow-500/40 bg-yellow-500/10",
  stale: "text-orange-300 border-orange-500/40 bg-orange-500/10",
  error: "text-red-300 border-red-500/40 bg-red-500/10",
  offline: "text-cyber-muted border-cyber-border bg-cyber-bg/40",
  starting: "text-blue-300 border-blue-500/40 bg-blue-500/10",
  unknown: "text-cyber-muted border-cyber-border",
};

function SystemPill({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyber-border/60 bg-cyber-bg/40 px-3 py-2">
      {ok ? (
        <Wifi className="w-4 h-4 text-cyber-accent shrink-0" />
      ) : (
        <WifiOff className="w-4 h-4 text-cyber-danger shrink-0" />
      )}
      <div className="min-w-0">
        <p className="text-xs text-white">{label}</p>
        {detail && <p className="text-[10px] text-cyber-muted truncate">{detail}</p>}
      </div>
    </div>
  );
}

function IntegrationRow({ probe }: { probe: IntegrationProbe }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs py-1.5 border-b border-cyber-border/40 last:border-0">
      <div className="flex items-center gap-2">
        <PlatformBadge platform={probe.platform} />
        <span className="text-cyber-muted">{probe.circuit_state}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {probe.latency_ms != null && (
          <span className="font-mono text-cyber-muted">{probe.latency_ms}ms</span>
        )}
        <Badge variant={probe.ok ? "default" : "danger"}>
          {probe.ok ? "OK" : "FAIL"}
        </Badge>
      </div>
    </div>
  );
}

function StreamRow({ row }: { row: PlatformHealthStream }) {
  return (
    <div className="rounded-lg border border-cyber-border/50 bg-cyber-bg/30 px-3 py-2 space-y-1">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <PlatformBadge platform={row.platform} />
          <span className="text-sm text-white truncate">{row.channel_name || row.slug}</span>
        </div>
        <span
          className={cn(
            "text-[10px] uppercase px-2 py-0.5 rounded border shrink-0",
            STATUS_STYLES[row.status] || STATUS_STYLES.unknown,
          )}
        >
          {row.status}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-cyber-muted font-mono">
        <span>viewers: {row.viewer_count}</span>
        <span>msg/min: {row.messages_per_min}</span>
        <span>reconn: {row.reconnect_count}</span>
        <span>
          socket: {row.socket_connected ? row.socket_transport || "on" : "off"}
        </span>
      </div>
      {row.ai_flags && row.ai_flags.length > 0 && (
        <p className="text-[10px] text-orange-300/90">
          IA: {row.ai_flags.join(", ")} ({Math.round(row.ai_anomaly_score)})
        </p>
      )}
    </div>
  );
}

export function PlatformMonitorHealthPanel({
  overview,
  loading,
}: {
  overview?: PlatformHealthOverview;
  loading?: boolean;
}) {
  if (!overview?.enabled && !loading) {
    return (
      <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4">
        <p className="text-sm text-cyber-muted">Monitoreo de salud desactivado.</p>
      </div>
    );
  }

  const sys = overview?.system;
  const summary = overview?.summary ?? {};

  return (
    <div className="rounded-xl border border-cyber-border/80 bg-cyber-surface/40 p-4 backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-cyber-accent" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wide">
            Salud monitores (Kick / YouTube / TikTok)
          </h3>
        </div>
        <Badge variant="info">{sys?.active_monitors ?? 0} activos</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <SystemPill
          label="Redis / PubSub"
          ok={!!sys?.redis_ok}
          detail={
            sys?.redis_latency_ms != null ? `${sys.redis_latency_ms} ms` : undefined
          }
        />
        <SystemPill
          label="Worker Render"
          ok={!!sys?.worker_alive}
          detail={sys?.worker_last_seen ?? "sin heartbeat"}
        />
        <SystemPill
          label="Orquestador"
          ok={!!sys?.orchestrator_running}
          detail={`proc: ${sys?.api_process ?? "—"}`}
        />
        <SystemPill
          label="Monitores"
          ok={(sys?.active_monitors ?? 0) > 0}
          detail={`${summary.healthy ?? 0} healthy`}
        />
      </div>

      <div className="flex flex-wrap gap-2 text-[10px]">
        {Object.entries(summary).map(([k, v]) => (
          <span
            key={k}
            className="px-2 py-1 rounded border border-cyber-border text-cyber-muted uppercase"
          >
            {k}: {v}
          </span>
        ))}
      </div>

      {overview?.integrations && overview.integrations.length > 0 && (
        <div className="rounded-lg border border-cyber-border/50 p-3">
          <p className="text-[10px] uppercase tracking-widest text-cyber-muted mb-2 flex items-center gap-1">
            <Server size={12} /> APIs externas
          </p>
          {overview.integrations.map((p) => (
            <IntegrationRow key={p.platform} probe={p} />
          ))}
        </div>
      )}

      <div className="space-y-2 max-h-72 overflow-y-auto">
        <p className="text-[10px] uppercase tracking-widest text-cyber-muted flex items-center gap-1">
          <Radio size={12} /> Streams monitoreados
        </p>
        {loading && (
          <p className="text-xs text-cyber-muted animate-pulse">Auditando monitores…</p>
        )}
        {!loading && (!overview?.streams || overview.streams.length === 0) && (
          <p className="text-xs text-cyber-muted">
            Sin streams activos. Activa SOC monitor en Channels y escanea un canal LIVE.
          </p>
        )}
        {overview?.streams?.map((s) => (
          <StreamRow key={s.stream_id} row={s} />
        ))}
      </div>

      {overview?.issues && overview.issues.length > 0 && (
        <div className="rounded-lg border border-cyber-danger/30 bg-cyber-danger/5 p-3 max-h-32 overflow-y-auto">
          <p className="text-[10px] uppercase text-cyber-danger mb-2">Incidencias recientes</p>
          {overview.issues.slice(0, 8).map((issue, i) => (
            <p key={i} className="text-[10px] text-cyber-muted">
              {String(issue.message ?? issue.flag ?? issue.at)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
