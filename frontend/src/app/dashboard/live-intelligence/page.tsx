"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Activity, Radio, TrendingUp, Users, type LucideIcon } from "lucide-react";
import { LiveGrowthChart } from "@/components/live-intel/LiveGrowthChart";
import { LiveIntelHeatmap } from "@/components/live-intel/LiveIntelHeatmap";
import { LiveIntelRankings } from "@/components/live-intel/LiveIntelRankings";
import { LiveStreamsTable } from "@/components/live-intel/LiveStreamsTable";
import { Badge } from "@/components/ui/badge";
import { useLiveIntel } from "@/hooks/useLiveIntel";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

export default function LiveIntelligencePage() {
  const accessToken = useApiToken();
  const {
    enabled,
    overview,
    displaySnapshots,
    streams,
    anomalies,
    loading,
  } = useLiveIntel();

  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<{
    rows: { channel_name: string; viewers: number; engagement_score: number; bot_probability: number }[];
    insights: string[];
  } | null>(null);

  const compareMutation = useMutation({
    mutationFn: () => api.liveIntelligence.compare(accessToken!, compareIds),
    onSuccess: (data) => setCompareResult(data),
  });

  const liveStreams = streams.filter((s) => s.is_live);

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-cyber-info/25 bg-gradient-to-r from-cyber-surface via-cyber-bg to-cyber-surface p-6 md:p-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Radio className="text-cyber-info" size={28} />
              <h1 className="text-2xl md:text-3xl font-bold text-white">
                Live Stream Intelligence
              </h1>
            </div>
            <p className="text-cyber-muted text-sm max-w-2xl">
              Monitoreo competitivo en tiempo real: Kick, YouTube Live, TikTok y Twitch.
              Detección de viewbots, engagement sintético y comparativas entre streamers externos.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="default">{overview?.live_count ?? 0} en vivo</Badge>
            <Badge variant={overview?.suspicious_live ? "danger" : "muted"}>
              {overview?.suspicious_live ?? 0} sospechosos
            </Badge>
            <Badge variant="muted">{streams.length} monitoreados</Badge>
          </div>
        </div>
      </div>

      {!enabled && (
        <p className="text-sm text-yellow-200 bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-4 py-3">
          LIVE_INTEL_ENABLED está desactivado en el servidor.
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat icon={Users} label="En vivo" value={overview?.live_count ?? 0} />
        <Stat icon={Activity} label="Engagement medio" value={overview?.avg_engagement?.toFixed(0) ?? "—"} />
        <Stat icon={TrendingUp} label="Monitoreados" value={overview?.monitored_count ?? streams.length} />
        <Stat icon={Radio} label="Anomalías recientes" value={anomalies.length} accent="danger" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-xl border border-cyber-border bg-cyber-surface/50">
            <div className="px-4 py-3 border-b border-cyber-border">
              <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
                Streams en vivo
              </h2>
            </div>
            {loading ? (
              <p className="p-6 text-cyber-muted text-sm">Cargando métricas…</p>
            ) : (
              <LiveStreamsTable snapshots={displaySnapshots} />
            )}
          </div>

          <div className="rounded-xl border border-cyber-border bg-cyber-surface/50">
            <div className="px-4 py-3 border-b border-cyber-border">
              <h2 className="text-sm font-semibold text-white">Crecimiento comparativo</h2>
            </div>
            <LiveGrowthChart snapshots={displaySnapshots} />
          </div>
        </div>

        <div className="space-y-4">
          <LiveIntelRankings
            title="Más sospechosos"
            entries={overview?.rankings_suspicious ?? []}
            variant="danger"
          />
          <LiveIntelRankings
            title="Engagement más orgánico"
            entries={overview?.rankings_organic ?? []}
          />
          <LiveIntelRankings
            title="Crecimiento anormal"
            entries={overview?.rankings_anomaly_growth ?? []}
            variant="danger"
          />
        </div>
      </div>

      <div className="rounded-xl border border-cyber-border bg-cyber-surface/50">
        <div className="px-4 py-3 border-b border-cyber-border">
          <h2 className="text-sm font-semibold text-white">Heatmap de actividad</h2>
        </div>
        <LiveIntelHeatmap heatmap={overview?.heatmap ?? []} />
      </div>

      <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 p-4">
        <h2 className="text-sm font-semibold text-white mb-3">Comparar streamers</h2>
        <div className="flex flex-wrap gap-2 mb-4">
          {liveStreams.map((s) => {
            const selected = compareIds.includes(s.stream_id);
            return (
              <button
                key={s.stream_id}
                type="button"
                onClick={() =>
                  setCompareIds((prev) =>
                    selected
                      ? prev.filter((id) => id !== s.stream_id)
                      : prev.length < 6
                        ? [...prev, s.stream_id]
                        : prev,
                  )
                }
                className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                  selected
                    ? "border-cyber-accent bg-cyber-accent/15 text-cyber-accent"
                    : "border-cyber-border text-cyber-muted hover:text-white"
                }`}
              >
                {s.channel_name}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          disabled={compareIds.length < 2 || compareMutation.isPending}
          onClick={() => compareMutation.mutate()}
          className="text-sm px-4 py-2 rounded-lg bg-cyber-accent/20 border border-cyber-accent/40 text-cyber-accent disabled:opacity-40"
        >
          Comparar selección ({compareIds.length})
        </button>
        {compareResult && (
          <div className="mt-4 space-y-2">
            {compareResult.insights.map((line, i) => (
              <p key={i} className="text-sm text-cyber-warning">
                {line}
              </p>
            ))}
            <div className="grid md:grid-cols-2 gap-2 mt-2">
              {compareResult.rows.map((r) => (
                <div
                  key={r.channel_name}
                  className="rounded-lg border border-cyber-border/60 px-3 py-2 text-sm"
                >
                  <p className="text-white font-medium">{r.channel_name}</p>
                  <p className="text-cyber-muted text-xs">
                    {r.viewers} viewers · engagement {r.engagement_score.toFixed(0)} · bot{" "}
                    {(r.bot_probability * 100).toFixed(0)}%
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {anomalies.length > 0 && (
        <div className="rounded-xl border border-cyber-danger/30 bg-cyber-danger/5 p-4">
          <h2 className="text-sm font-semibold text-cyber-danger mb-2">Alertas recientes</h2>
          <ul className="space-y-1 text-sm text-white/90">
            {anomalies.slice(0, 8).map((a, i) => (
              <li key={i}>
                {a.channel_name || a.stream_id} — {a.type}{" "}
                {a.viewbot_probability != null
                  ? `(${(a.viewbot_probability * 100).toFixed(0)}% viewbot)`
                  : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  accent?: "danger";
}) {
  return (
    <div className="rounded-xl border border-cyber-border bg-cyber-surface/50 p-4">
      <Icon
        size={20}
        className={accent === "danger" ? "text-cyber-danger mb-2" : "text-cyber-info mb-2"}
      />
      <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      <p className="text-[10px] uppercase text-cyber-muted tracking-wider">{label}</p>
    </div>
  );
}
