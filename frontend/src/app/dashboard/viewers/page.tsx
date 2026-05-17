"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, MessageSquare, RefreshCw, Scan, Shield, Users, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { api, type Stream, type Viewer } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import clsx from "clsx";

type ViewFilter = "all" | "talking" | "suspected";

function ViewersContent() {
  const searchParams = useSearchParams();
  const { accessToken } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();
  const [selectedStream, setSelectedStream] = useState(searchParams.get("stream") ?? "");
  const [viewFilter, setViewFilter] = useState<ViewFilter>("all");
  const [message, setMessage] = useState("");
  const lastQuickSyncStream = useRef<string | null>(null);

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
    refetchInterval: 20000,
  });

  const streamId = selectedStream || streams[0]?.id || "";
  const currentStream = streams.find((s) => s.id === streamId);

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
    queryKey: ["viewers", streamId, viewFilter],
    queryFn: () => api.streams.viewers(token, streamId, viewFilter),
    enabled: !!token && !!streamId,
    refetchInterval: 15000,
  });

  const quickSyncMutation = useMutation({
    mutationFn: () => api.streams.syncQuick(token, streamId),
    onSuccess: (res) => {
      if (res.status === "offline") return;
      setMessage(
        res.note
          ? res.note
          : `Sincronizado: ${res.chatters_synced ?? 0} en chat · ${res.talking_count ?? 0} hablando · ${res.suspected_count ?? 0} sospechosos`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
  });

  useEffect(() => {
    if (!streamId || !currentStream?.is_live || quickSyncMutation.isPending) return;
    if (lastQuickSyncStream.current === streamId) return;
    lastQuickSyncStream.current = streamId;
    quickSyncMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- auto-sync once per stream when live
  }, [streamId, currentStream?.is_live]);

  useEffect(() => {
    lastQuickSyncStream.current = null;
  }, [streamId]);

  const scanMutation = useMutation({
    mutationFn: () => api.streams.monitor(token, streamId),
    onSuccess: (res) => {
      setViewFilter("all");
      setMessage(
        res.status === "offline"
          ? "Canal offline — no hay chat que escanear"
          : `Escaneo completo: ${res.chatters_synced ?? 0} en chat · ${res.suspected_count ?? 0} sospechosos${
              res.attack_created ? " · posible ataque detectado" : ""
            }`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
      queryClient.invalidateQueries({ queryKey: ["attacks"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const mitigateMutation = useMutation({
    mutationFn: () => {
      const attacks = queryClient.getQueryData<{ id: string; status: string }[]>([
        "attacks-active",
        streamId,
      ]);
      const active = attacks?.find((a) => a.status === "active");
      if (!active) throw new Error("No hay ataques activos en este canal");
      return api.attacks.mitigate(token, active.id, { full_mitigation: true });
    },
    onSuccess: (res: { bans_created?: number; targets?: number }) => {
      setMessage(
        `Ataque mitigado: ${res.targets ?? 0} objetivos bloqueados (${res.bans_created ?? 0} bans)`,
      );
      queryClient.invalidateQueries({ queryKey: ["attacks-active"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  useQuery({
    queryKey: ["attacks-active", streamId],
    queryFn: () => api.attacks.list(token, "active", streamId),
    enabled: !!token && !!streamId,
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
  const talkingCount = monitorStatus?.talking_count ?? viewers.filter((v) => (v.chat_messages ?? 0) > 0).length;
  const suspectedCount = monitorStatus?.suspected_bots ?? viewers.filter((v) => v.is_suspected_bot).length;
  const twitchViewers = monitorStatus?.viewer_count ?? currentStream?.viewer_count ?? 0;
  const silentBots = monitorStatus?.silent_viewbots_estimate ?? 0;
  const proxyIps = monitorStatus?.proxy_ips_detected ?? 0;
  const activeAttacks = monitorStatus?.active_attacks ?? 0;
  const syncing = quickSyncMutation.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-info" />
          Usuarios del stream
        </h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-3xl">
          Solo usuarios reales en el chat del stream (IRC/Helix). No se listan pings del widget ni
          bots de Twitch (Nightbot, StreamElements, etc.). Viewers totales en Twitch:{" "}
          <strong className="text-white">{twitchViewers || "—"}</strong>
          {silentBots > 0 && (
            <>
              {" "}
              · posibles viewbots silenciosos:{" "}
              <strong className="text-cyber-danger">~{silentBots}</strong>
            </>
          )}
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyber-accent border border-cyber-accent/30 rounded-lg px-4 py-2">
          {message}
        </p>
      )}

      {monitorStatus && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Viewers Twitch" value={String(twitchViewers)} />
          <Stat label="En chat" value={String(totalInChat)} highlight={syncing} />
          <Stat label="Hablando" value={String(talkingCount)} />
          <Stat label="Sospechosos" value={String(suspectedCount)} highlight={suspectedCount > 0} danger />
          <Stat label="IPs proxy" value={String(proxyIps)} highlight={proxyIps > 0} danger />
        </div>
      )}

      {!monitorStatus?.has_broadcaster_oauth && currentStream?.monitor_mode && (
        <p className="text-xs text-cyber-muted border border-cyber-border rounded-lg px-3 py-2">
          Sin OAuth del streamer la sync rapida es limitada. Usa{" "}
          <Link href="/dashboard/channels" className="text-cyber-accent hover:underline">
            Invitar streamer
          </Link>{" "}
          para listar todo el chat al cargar, o escaneo IRC completo.
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
          disabled={!streamId || !currentStream?.is_live || quickSyncMutation.isPending}
          onClick={() => quickSyncMutation.mutate()}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-cyber-muted text-sm hover:text-white disabled:opacity-50"
        >
          <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Sincronizando..." : "Resincronizar"}
        </button>
        <button
          type="button"
          disabled={!streamId || scanMutation.isPending}
          onClick={() => scanMutation.mutate()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm disabled:opacity-50"
        >
          <Scan size={16} />
          {scanMutation.isPending ? "Escaneando (~55s)..." : "Escanear chat (hablantes + bots)"}
        </button>
        {activeAttacks > 0 && (
          <button
            type="button"
            disabled={mitigateMutation.isPending}
            onClick={() => mitigateMutation.mutate()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-danger/20 text-cyber-danger border border-cyber-danger/40 text-sm"
          >
            <Shield size={16} />
            Mitigar ataque ({activeAttacks})
          </button>
        )}
        <div className="flex rounded-lg border border-cyber-border overflow-hidden text-sm">
          <FilterTab
            active={viewFilter === "all"}
            onClick={() => setViewFilter("all")}
            label={`Todos (${totalInChat})`}
          />
          <FilterTab
            active={viewFilter === "talking"}
            onClick={() => setViewFilter("talking")}
            label={`Hablando (${talkingCount})`}
            border
          />
          <FilterTab
            active={viewFilter === "suspected"}
            onClick={() => setViewFilter("suspected")}
            label={`Sospechosos (${suspectedCount})`}
            border
            danger
          />
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
                <td className="py-3 px-2 text-center text-cyber-muted">
                  {(v.chat_messages ?? 0) > 0 ? (
                    <span className="inline-flex items-center gap-1 text-cyber-accent">
                      <MessageSquare size={12} /> {v.chat_messages}
                    </span>
                  ) : (
                    "0"
                  )}
                </td>
                <td className="py-3 px-2 text-center text-xs">
                  {v.is_suspected_bot ? (
                    <span className="text-cyber-danger">Sospechoso / bot</span>
                  ) : (v.chat_messages ?? 0) > 0 ? (
                    <span className="text-cyber-accent">Hablando</span>
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
        {streamId && !currentStream?.is_live && (
          <p className="text-center py-12 text-cyber-muted">Canal offline — entra cuando este en vivo</p>
        )}
        {streamId && currentStream?.is_live && !isLoading && viewers.length === 0 && (
          <p className="text-center py-12 text-cyber-muted">
            {syncing
              ? "Sincronizando usuarios del chat..."
              : "Sin usuarios aun — pulsa Resincronizar o Escanear chat"}
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

function Stat({
  label,
  value,
  highlight,
  danger,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="cyber-card py-3 px-4">
      <p className="text-xs text-cyber-muted">{label}</p>
      <p
        className={clsx(
          "text-xl font-bold",
          danger && highlight ? "text-cyber-danger" : highlight ? "text-cyber-accent" : "text-white",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function FilterTab({
  active,
  onClick,
  label,
  border,
  danger,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  border?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "px-3 py-2",
        border && "border-l border-cyber-border",
        active
          ? danger
            ? "bg-cyber-danger/20 text-cyber-danger"
            : "bg-cyber-accent/20 text-cyber-accent"
          : "text-cyber-muted",
      )}
    >
      {label}
    </button>
  );
}

export default function ViewersPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-6">Cargando...</p>}>
      <ViewersContent />
    </Suspense>
  );
}
