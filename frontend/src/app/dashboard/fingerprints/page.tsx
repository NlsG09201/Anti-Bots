"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Fingerprint as FingerprintIcon, Radio, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { PlatformBadge } from "@/components/PlatformBadge";
import clsx from "clsx";

export default function FingerprintsPage() {
  const accessToken = useApiToken();
  const [streamFilter, setStreamFilter] = useState("");
  const [hashQuery, setHashQuery] = useState("");
  const [minRiskOnly, setMinRiskOnly] = useState(false);

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(accessToken!),
    enabled: !!accessToken,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["fingerprints", streamFilter, hashQuery, minRiskOnly],
    queryFn: () =>
      api.fingerprints.list(accessToken!, {
        stream_id: streamFilter || undefined,
        q: hashQuery.trim() || undefined,
        min_risk: minRiskOnly ? 50 : 0,
        limit: 200,
      }),
    enabled: !!accessToken,
  });

  const fingerprints = data?.fingerprints ?? [];

  const selectedChannel = useMemo(
    () => streams.find((s) => s.id === streamFilter),
    [streams, streamFilter],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <FingerprintIcon className="text-cyber-accent" size={26} />
          Device Fingerprints
        </h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-3xl">
          Huellas capturadas por widget, eventos o sesiones de viewers. Filtra por canal o busca por
          hash para ver en qué streams apareció cada dispositivo.
        </p>
      </div>

      <div className="cyber-card p-4 flex flex-wrap gap-4 items-end">
        <label className="flex flex-col gap-1 min-w-[200px] flex-1">
          <span className="text-xs text-cyber-muted uppercase tracking-wide">Canal</span>
          <div className="relative">
            <Radio
              className="absolute left-3 top-1/2 -translate-y-1/2 text-cyber-muted"
              size={16}
            />
            <select
              value={streamFilter}
              onChange={(e) => setStreamFilter(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-cyber-border bg-cyber-bg text-white text-sm cursor-pointer"
            >
              <option value="">Todos los canales</option>
              {streams.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.channel_name} {s.is_live ? "(live)" : ""}
                </option>
              ))}
            </select>
          </div>
        </label>

        <label className="flex flex-col gap-1 min-w-[220px] flex-[2]">
          <span className="text-xs text-cyber-muted uppercase tracking-wide">Buscar hash</span>
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-cyber-muted"
              size={16}
            />
            <input
              type="search"
              value={hashQuery}
              onChange={(e) => setHashQuery(e.target.value)}
              placeholder="Ej. a3f2b9… (parcial)"
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-cyber-border bg-cyber-bg text-white text-sm font-mono"
            />
          </div>
        </label>

        <label className="flex items-center gap-2 text-sm text-cyber-muted cursor-pointer pb-2">
          <input
            type="checkbox"
            checked={minRiskOnly}
            onChange={(e) => setMinRiskOnly(e.target.checked)}
            className="rounded border-cyber-border cursor-pointer"
          />
          Solo riesgo ≥ 50
        </label>
      </div>

      {selectedChannel && (
        <p className="text-xs text-cyber-muted">
          Mostrando fingerprints detectados en{" "}
          <span className="text-white">{selectedChannel.channel_name}</span>
          {selectedChannel.monitor_mode && (
            <span className="text-orange-300"> · modo observación</span>
          )}
        </p>
      )}

      <div className="cyber-card overflow-x-auto">
        {isLoading && (
          <p className="p-6 text-sm text-cyber-muted">Cargando fingerprints…</p>
        )}
        {!isLoading && fingerprints.length === 0 && (
          <p className="p-6 text-sm text-cyber-muted">
            No hay fingerprints para este filtro. Usa el widget en el canal o genera eventos con
            detección avanzada; el listado IRC por sí solo no crea huellas.
          </p>
        )}
        {!isLoading && fingerprints.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-cyber-muted border-b border-cyber-border">
                <th className="text-left py-3 px-4">Hash</th>
                <th className="text-left py-3 px-4">Canales</th>
                <th className="text-right py-3 px-4">Risk</th>
                <th className="text-center py-3 px-4">Headless</th>
                <th className="text-right py-3 px-4">Eventos</th>
                <th className="text-left py-3 px-4">Flags</th>
                <th className="text-center py-3 px-4">Blocked</th>
              </tr>
            </thead>
            <tbody>
              {fingerprints.map((fp) => (
                <tr
                  key={fp.hash}
                  className="border-b border-cyber-border/50 hover:bg-cyber-bg/40"
                >
                  <td className="py-3 px-4 font-mono text-xs text-white" title={fp.hash}>
                    {fp.hash.slice(0, 20)}…
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex flex-wrap gap-1.5">
                      {(fp.channels ?? []).map((ch) => (
                        <button
                          key={ch.stream_id}
                          type="button"
                          onClick={() => setStreamFilter(ch.stream_id)}
                          className={clsx(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs cursor-pointer",
                            streamFilter === ch.stream_id
                              ? "border-cyber-accent/50 bg-cyber-accent/10 text-cyber-accent"
                              : "border-cyber-border text-cyber-muted hover:text-white",
                          )}
                        >
                          <PlatformBadge platform={ch.platform} />
                          {ch.channel_name}
                        </button>
                      ))}
                      {(fp.channels?.length ?? 0) === 0 && (
                        <span className="text-cyber-muted text-xs">—</span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right font-mono text-cyber-danger">
                    {fp.risk_score.toFixed(0)}
                  </td>
                  <td className="py-3 px-4 text-center">{fp.is_headless ? "⚠" : "—"}</td>
                  <td className="py-3 px-4 text-right">{fp.event_count ?? 0}</td>
                  <td className="py-3 px-4 text-xs text-cyber-muted max-w-[180px] truncate">
                    {fp.automation_flags.join(", ") || "—"}
                  </td>
                  <td className="py-3 px-4 text-center">{fp.is_blocked ? "🚫" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!isLoading && fingerprints.length > 0 && (
        <p className="text-xs text-cyber-muted">
          {data?.count ?? fingerprints.length} resultado(s)
          {streamFilter ? " en el canal seleccionado" : " en todos tus canales"}
        </p>
      )}
    </div>
  );
}
