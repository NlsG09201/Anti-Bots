"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Brain,
  Link2,
  MessageSquare,
  RefreshCw,
  Scan,
  Shield,
  Users,
  AlertTriangle,
} from "lucide-react";
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
  const [inviteUrl, setInviteUrl] = useState("");
  const lastFullLoadStream = useRef<string | null>(null);

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
    if (searchParams.get("twitch") === "connected") {
      setMessage("Streamer conectado. Cargando listado Helix completo...");
      lastFullLoadStream.current = null;
      queryClient.invalidateQueries({ queryKey: ["streams"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    }
  }, [searchParams, queryClient]);

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

  const inviteMutation = useMutation({
    mutationFn: () => api.streams.channelInvite(token, streamId),
    onSuccess: (data) => {
      setInviteUrl(data.invite_url);
      setMessage(
        `Enlace para @${data.channel_login} copiado. El streamer debe abrirlo e iniciar sesion en Twitch.`,
      );
      navigator.clipboard?.writeText(data.invite_url);
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const fullLoadMutation = useMutation({
    mutationFn: () => api.streams.loadFullViewers(token, streamId),
    onSuccess: (res) => {
      if (res.status === "offline") {
        setMessage(res.message || "Canal offline");
        return;
      }
      setViewFilter("all");
      setMessage(
        res.message ||
          `Listado: ${res.chatters_synced ?? 0} en chat / ${res.viewer_count ?? 0} viewers Twitch`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  useEffect(() => {
    if (!streamId || !currentStream?.is_live || fullLoadMutation.isPending) return;
    if (lastFullLoadStream.current === streamId) return;
    lastFullLoadStream.current = streamId;
    fullLoadMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- auto load full list once per live stream
  }, [streamId, currentStream?.is_live]);

  useEffect(() => {
    lastFullLoadStream.current = null;
  }, [streamId]);

  const aiScreenMutation = useMutation({
    mutationFn: () => api.streams.screenViewers(token, streamId),
    onSuccess: (res) => {
      const ti = res.twitch_insights_matched ?? 0;
      const db = res.twitch_insights_db_size ?? 0;
      setMessage(
        `IA + Twitch Insights (${db} bots conocidos): ${res.screened} analizados · ` +
          `${res.flagged} maliciosos · ${ti} en base Twitch Insights`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

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

  const banSuspectedMutation = useMutation({
    mutationFn: () =>
      api.streams.banSuspected(token, streamId, { apply_twitch_ban: true, duration_hours: 24 }),
    onSuccess: (res) => {
      setMessage(
        `Bloqueados ${res.targets} sospechosos · ${res.bans_created} bans · ` +
          `${res.twitch_bans_applied} bans en Twitch`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["attacks-active"] });
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
    onSuccess: (res: { bans_created?: number; targets?: number; twitch_bans_applied?: number }) => {
      setMessage(
        `Ataque mitigado: ${res.targets ?? 0} objetivos · ${res.bans_created ?? 0} bans` +
          (res.twitch_bans_applied ? ` · ${res.twitch_bans_applied} en Twitch` : ""),
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
  const syncing = fullLoadMutation.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-info" />
          Usuarios del stream
        </h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-3xl">
          Listado completo del chat del canal (Helix + IRC ~50s). Twitch no expone viewers
          silenciosos por API — solo quien esta en la sala de chat. Viewers totales:{" "}
          <strong className="text-white">{twitchViewers || "—"}</strong>
          {monitorStatus?.active_viewers_tracked != null && twitchViewers > 0 && (
            <>
              {" "}
              · en chat: <strong className="text-cyber-accent">{totalInChat}</strong>
            </>
          )}
          {silentBots > 0 && (
            <>
              {" "}
              · no visibles en chat:{" "}
              <strong className="text-cyber-danger">~{silentBots}</strong>
            </>
          )}
          {currentStream?.monitor_mode && !monitorStatus?.has_broadcaster_oauth && (
            <>
              {" "}
              · <Link href="/dashboard/channels" className="text-cyber-accent hover:underline">
                Invita al streamer
              </Link>{" "}
              para listado Helix completo en canal ajeno
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

      {inviteUrl && (
        <p className="text-xs text-cyber-muted break-all border border-cyber-border rounded-lg p-3">
          Enlace invitacion: {inviteUrl}
        </p>
      )}

      {currentStream?.monitor_mode && !monitorStatus?.has_broadcaster_oauth && (
        <div className="cyber-card p-4 border border-cyber-info/30 bg-cyber-info/5">
          <p className="text-sm text-white font-medium mb-2">
            Canal ajeno — listado Helix completo
          </p>
          <p className="text-xs text-cyber-muted mb-3">
            Sin OAuth del streamer solo veras parte del chat (IRC). Genera un enlace para que el
            streamer autorice StreamShield y cargues <strong className="text-white">todos</strong>{" "}
            los usuarios en chat al instante.
          </p>
          <button
            type="button"
            disabled={!streamId || inviteMutation.isPending}
            onClick={() => inviteMutation.mutate()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-info/20 text-cyber-info border border-cyber-info/40 text-sm"
          >
            <Link2 size={16} />
            {inviteMutation.isPending ? "Generando..." : "Generar enlace Invitar streamer"}
          </button>
        </div>
      )}

      {monitorStatus?.has_broadcaster_oauth && currentStream?.monitor_mode && (
        <p className="text-xs text-cyber-accent border border-cyber-accent/30 rounded-lg px-3 py-2">
          Helix conectado — &quot;Cargar listado completo&quot; usa la API oficial de chatters de
          Twitch.
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
          disabled={!streamId || !currentStream?.is_live || fullLoadMutation.isPending}
          onClick={() => fullLoadMutation.mutate()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm disabled:opacity-50"
        >
          <Users size={16} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Cargando listado (~50s)..." : "Cargar listado completo"}
        </button>
        <button
          type="button"
          disabled={!streamId || scanMutation.isPending}
          onClick={() => scanMutation.mutate()}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-cyber-muted text-sm hover:text-white disabled:opacity-50"
        >
          <Scan size={16} />
          {scanMutation.isPending ? "Analizando..." : "Escanear + detectar ataques"}
        </button>
        <button
          type="button"
          disabled={!streamId || aiScreenMutation.isPending || viewers.length === 0}
          onClick={() => aiScreenMutation.mutate()}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-sm text-cyber-muted hover:text-white disabled:opacity-50"
        >
          <Brain size={16} className={aiScreenMutation.isPending ? "animate-pulse" : ""} />
          {aiScreenMutation.isPending ? "Analizando..." : "Verificar bots (Insights + IA)"}
        </button>
        {suspectedCount > 0 && (
          <button
            type="button"
            disabled={banSuspectedMutation.isPending}
            onClick={() => banSuspectedMutation.mutate()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-950/40 text-red-300 border border-red-500/40 text-sm disabled:opacity-50"
          >
            <Ban size={16} />
            {banSuspectedMutation.isPending
              ? "Baneando..."
              : `Banear sospechosos (${suspectedCount})`}
          </button>
        )}
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
                <td className="py-3 px-2 text-center text-xs max-w-[220px]">
                  {v.is_suspected_bot ? (
                    <div>
                      <span className="text-cyber-danger block">
                        {(v.behavior_metrics?.ai_verdict as { source?: string })?.source ===
                        "twitch_insights"
                          ? "Viewbot (Twitch Insights)"
                          : "Bot / malicioso"}
                      </span>
                      <span
                        className="text-cyber-muted text-[10px] line-clamp-2"
                        title={String(
                          (v.behavior_metrics?.ai_verdict as { risk_description?: string })
                            ?.risk_description ?? "",
                        )}
                      >
                        {(
                          v.behavior_metrics?.ai_verdict as { risk_description?: string }
                        )?.risk_description ||
                          "Patron sospechoso detectado"}
                      </span>
                    </div>
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
              ? "Cargando listado completo del stream..."
              : "Sin usuarios — pulsa Cargar listado completo (canal en vivo)"}
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
