"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, RefreshCw, Scan, Users, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { api, type Stream, type Viewer } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import clsx from "clsx";

type ViewFilter = "all" | "suspected";

function ViewersContent() {
  const searchParams = useSearchParams();
  const { accessToken } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();
  const [selectedStream, setSelectedStream] = useState(searchParams.get("stream") ?? "");
  const [viewFilter, setViewFilter] = useState<ViewFilter>("all");
  const [message, setMessage] = useState("");

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
    refetchInterval: 20000,
  });

  const streamId = selectedStream || streams[0]?.id || "";
  const currentStream = streams.find((s) => s.id === streamId);
  const suspectedOnly = viewFilter === "suspected";

  useEffect(() => {
    const q = searchParams.get("stream");
    if (q) setSelectedStream(q);
  }, [searchParams]);

  const { data: monitorStatus } = useQuery({
    queryKey: ["monitor-status", streamId],
    queryFn: () => api.streams.monitorStatus(token, streamId),
    enabled: !!token && !!streamId,
    refetchInterval: 15000,
  });

  const { data: viewers = [], isLoading } = useQuery({
    queryKey: ["viewers", streamId, suspectedOnly],
    queryFn: () => api.streams.viewers(token, streamId, suspectedOnly),
    enabled: !!token && !!streamId,
    refetchInterval: 15000,
  });

  const scanMutation = useMutation({
    mutationFn: () => api.streams.monitor(token, streamId),
    onSuccess: (res) => {
      setViewFilter("all");
      setMessage(
        res.status === "offline"
          ? "Canal offline — no hay chat que escanear"
          : `Listado completo: ${res.chatters_synced ?? 0} usuarios en chat · ${res.suspected_count ?? 0} sospechosos${
              res.attack_created ? " · posible ataque" : ""
            }`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
      queryClient.invalidateQueries({ queryKey: ["attacks"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const blockMutation = useMutation({
    mutationFn: (viewer: Viewer) =>
      api.streams.blockViewer(token, streamId, viewer.id, {
        reason: "Bloqueado desde panel SOC — actividad sospechosa",
        duration_hours: 24,
        apply_twitch_ban: !currentStream?.monitor_mode,
      }),
    onSuccess: (res) => {
      setMessage(res.message || "Usuario bloqueado");
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const totalInChat = monitorStatus?.active_viewers_tracked ?? viewers.length;
  const suspectedCount = monitorStatus?.suspected_bots ?? viewers.filter((v) => v.is_suspected_bot).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-info" />
          Usuarios en el chat
        </h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-2xl">
          Tras escanear veras <strong className="text-white">todos</strong> los usuarios detectados en el chat.
          Usa la pestana &quot;Solo sospechosos&quot; para filtrar. Viewers totales en Twitch:{" "}
          {monitorStatus?.viewer_count ?? "—"} (incluye quien no escribe en chat).
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyber-accent border border-cyber-accent/30 rounded-lg px-4 py-2">
          {message}
        </p>
      )}

      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-cyber-muted block mb-1">Canal</label>
          <select
            value={streamId}
            onChange={(e) => setSelectedStream(e.target.value)}
            className="bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white min-w-[200px]"
          >
            {streams.map((s: Stream) => (
              <option key={s.id} value={s.id}>
                {s.channel_name}
                {s.monitor_mode ? " (obs)" : ""}
                {s.is_live ? " LIVE" : ""}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          disabled={!streamId || scanMutation.isPending}
          onClick={() => scanMutation.mutate()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm disabled:opacity-50"
        >
          <Scan size={16} />
          {scanMutation.isPending ? "Escaneando (~55s)..." : "Escanear chat completo"}
        </button>
        <div className="flex rounded-lg border border-cyber-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setViewFilter("all")}
            className={clsx(
              "px-3 py-2",
              viewFilter === "all" ? "bg-cyber-accent/20 text-cyber-accent" : "text-cyber-muted",
            )}
          >
            Todos ({totalInChat})
          </button>
          <button
            type="button"
            onClick={() => setViewFilter("suspected")}
            className={clsx(
              "px-3 py-2 border-l border-cyber-border",
              viewFilter === "suspected" ? "bg-cyber-danger/20 text-cyber-danger" : "text-cyber-muted",
            )}
          >
            Solo sospechosos ({suspectedCount})
          </button>
        </div>
        <Link
          href={`/dashboard/attacks?stream=${streamId}`}
          className="text-sm text-cyber-accent hover:underline flex items-center gap-1 pb-2"
        >
          <AlertTriangle size={14} /> Ataques
        </Link>
      </div>

      <div className="cyber-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border">
              <th className="text-left py-3 px-2">Usuario</th>
              <th className="text-left py-3 px-2">Fuente</th>
              <th className="text-right py-3 px-2">Risk</th>
              <th className="text-center py-3 px-2">Msgs</th>
              <th className="text-center py-3 px-2">Estado</th>
              <th className="text-right py-3 px-2">Accion</th>
            </tr>
          </thead>
          <tbody>
            {viewers.map((v) => (
              <tr
                key={v.id}
                className={clsx(
                  "border-b border-cyber-border/50 hover:bg-cyber-bg/30",
                  v.is_suspected_bot && "bg-cyber-danger/5",
                )}
              >
                <td className="py-3 px-2 text-white font-medium">
                  {v.platform_username || v.platform_user_id || "—"}
                </td>
                <td className="py-3 px-2 text-cyber-muted text-xs">
                  {(v.behavior_metrics?.source as string) || "chat"}
                </td>
                <td className="py-3 px-2 text-right font-mono text-cyber-danger">
                  {v.risk_score.toFixed(0)}
                </td>
                <td className="py-3 px-2 text-center text-cyber-muted">{v.chat_messages ?? 0}</td>
                <td className="py-3 px-2 text-center text-xs">
                  {v.is_suspected_bot ? (
                    <span className="text-cyber-danger">Sospechoso</span>
                  ) : (
                    <span className="text-cyber-muted">En chat</span>
                  )}
                </td>
                <td className="py-3 px-2 text-right">
                  {v.is_suspected_bot && (
                    <button
                      type="button"
                      disabled={blockMutation.isPending}
                      onClick={() => blockMutation.mutate(v)}
                      className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-cyber-danger/50 text-cyber-danger"
                    >
                      <Ban size={12} /> Bloquear
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!streamId && (
          <p className="text-center py-12 text-cyber-muted">
            Anade un canal en <Link href="/dashboard/channels" className="text-cyber-accent">Channels</Link>
          </p>
        )}
        {streamId && !isLoading && viewers.length === 0 && viewFilter === "all" && (
          <p className="text-center py-12 text-cyber-muted">
            Pulsa &quot;Escanear chat completo&quot; con el canal en vivo (~55 s)
          </p>
        )}
        {streamId && !isLoading && viewers.length === 0 && viewFilter === "suspected" && (
          <p className="text-center py-12 text-cyber-muted">
            Ningun sospechoso en el ultimo escaneo. Prueba la pestana Todos.
          </p>
        )}
        {isLoading && (
          <p className="text-center py-8 text-cyber-muted flex items-center justify-center gap-2">
            <RefreshCw size={14} className="animate-spin" /> Cargando...
          </p>
        )}
      </div>
    </div>
  );
}

export default function ViewersPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-6">Cargando...</p>}>
      <ViewersContent />
    </Suspense>
  );
}
