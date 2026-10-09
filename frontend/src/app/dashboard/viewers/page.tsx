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
import { useApiToken } from "@/stores/authStore";
import clsx from "clsx";

type ViewFilter = "all" | "talking" | "suspected";

function viewerAssessment(viewer: Viewer): { label: string; detail: string; tone: string } {
  const verdict = viewer.behavior_metrics?.ai_verdict as
    | {
        classification?: string;
        risk_description?: string;
        source?: string;
        confidence?: number;
      }
    | undefined;

  if (verdict?.classification === "known_bot") {
    return {
      label: "Bot conocido",
      detail: `${verdict.risk_description || `Fuente verificada: ${verdict.source || "base de bots"}`}${verdict.confidence != null ? ` · confianza ${Math.round(verdict.confidence * 100)}%` : ""}`,
      tone: "text-cyber-danger",
    };
  }
  if (verdict?.classification === "review" || viewer.is_suspected_bot) {
    return {
      label: "Revisión recomendada",
      detail: verdict?.risk_description || "Señales heurísticas; no confirman automatización.",
      tone: "text-amber-400",
    };
  }
  if (verdict) {
    return {
      label: "Sin señales fuertes",
      detail: "No equivale a confirmar que sea una persona real.",
      tone: "text-cyber-accent",
    };
  }
  return {
    label: "Pendiente de analizar",
    detail: "Usa “Analizar señales de bots” para cruzar las fuentes disponibles.",
    tone: "text-cyber-muted",
  };
}

function platformLabel(platform?: string): string {
  const labels: Record<string, string> = {
    twitch: "Twitch",
    kick: "Kick",
    youtube: "YouTube",
    tiktok: "TikTok",
  };
  return labels[platform?.toLowerCase() ?? ""] ?? "plataforma";
}

function ViewersContent() {
  const searchParams = useSearchParams();
  const token = useApiToken();
  const queryClient = useQueryClient();
  const [selectedStream, setSelectedStream] = useState(searchParams.get("stream") ?? "");
  const [viewFilter, setViewFilter] = useState<ViewFilter>("all");
  const [message, setMessage] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [loadPhase, setLoadPhase] = useState<"idle" | "quick" | "full">("idle");
  const [j48Source, setJ48Source] = useState<"mixed" | "registered_bots" | "channel_flow">("mixed");
  const lastFullLoadStream = useRef<string | null>(null);
  const fullLoadInFlight = useRef(false);

  const handleStreamSelect = (id: string) => {
    lastFullLoadStream.current = null;
    setSelectedStream(id);
    setViewFilter("all");
    setMessage("");
  };

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    // El listado se refresca desde la BD. La sincronización externa se ejecuta
    // al seleccionar/recargar un canal, evitando llamadas a cada plataforma cada 20 s.
    queryFn: () => api.streams.list(token, false),
    enabled: !!token,
    refetchInterval: 20000,
  });

  const streamId = selectedStream || streams[0]?.id || "";
  const currentStream = streams.find((s) => s.id === streamId);

  useEffect(() => {
    const q = searchParams.get("stream");
    if (q) setSelectedStream(q);
    if (searchParams.get("twitch") === "connected") {
      lastFullLoadStream.current = null;
      queryClient.invalidateQueries({ queryKey: ["streams"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    }
  }, [searchParams, queryClient]);

  const { data: monitorStatus } = useQuery({
    queryKey: ["monitor-status", streamId],
    queryFn: () => api.streams.monitorStatus(token, streamId),
    enabled: !!token && !!streamId,
    refetchInterval: 30000,
  });

  const { data: viewers = [], isLoading } = useQuery({
    queryKey: ["viewers", streamId, viewFilter],
    queryFn: () => api.streams.viewers(token, streamId, viewFilter),
    enabled: !!token && !!streamId,
    refetchInterval: 30000,
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
    mutationFn: (id: string) => api.streams.loadFullViewers(token, id),
    onSuccess: (res) => {
      if (res.status === "offline") {
        setMessage(res.message || "Canal offline");
        queryClient.invalidateQueries({ queryKey: ["viewers"] });
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
    onError: (e: Error) => {
      setMessage(e.message);
      setLoadPhase("idle");
    },
    onSettled: () => {
      setLoadPhase("idle");
      fullLoadInFlight.current = false;
    },
  });

  const triggerFullLoad = async (id: string, force = false) => {
    if (!id || !token) return;
    if (fullLoadInFlight.current) return;
    if (!force && lastFullLoadStream.current === id) return;
    fullLoadInFlight.current = true;
    lastFullLoadStream.current = id;
    setViewFilter("all");

    const platform = currentStream?.platform?.toLowerCase();
    if (!platform) {
      fullLoadInFlight.current = false;
      return;
    }
    if (platform !== "twitch") {
      if (platform !== "kick" && platform !== "youtube") {
        setMessage(`El listado de participantes aún no está disponible para ${platform}.`);
        setLoadPhase("idle");
        fullLoadInFlight.current = false;
        return;
      }
      setLoadPhase("quick");
      setMessage(`Sincronizando participantes del chat de ${platform}…`);
      try {
        const sync = await api.streams.syncPlatform(token, id);
        const analysis = await api.streams.screenViewers(token, id);
        await queryClient.invalidateQueries({ queryKey: ["viewers", id] });
        await queryClient.invalidateQueries({ queryKey: ["monitor-status", id] });
        await queryClient.invalidateQueries({ queryKey: ["streams"] });
        setMessage(
          `${sync.chatters_synced ?? 0} participantes de chat de ${platform} analizados: ` +
            `${analysis.flagged} coincidencias conocidas, ${analysis.review_required ?? 0} para revisar. ` +
            "Los espectadores silenciosos no son identificables por la plataforma.",
        );
      } catch (e) {
        setMessage(e instanceof Error ? e.message : `No se pudo sincronizar ${platform}`);
      } finally {
        setLoadPhase("idle");
        fullLoadInFlight.current = false;
      }
      return;
    }

    setLoadPhase("quick");
    setMessage("Sincronizando participantes del chat (Helix)…");
    try {
      const quick = await api.streams.syncQuick(token, id);
      await queryClient.invalidateQueries({ queryKey: ["viewers"] });
      await queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
      await queryClient.invalidateQueries({ queryKey: ["streams"] });
      if (quick.status === "offline") {
        setMessage(quick.message || "Canal offline");
        setLoadPhase("idle");
        fullLoadInFlight.current = false;
        return;
      }
      const inChat = quick.chatters_synced ?? 0;
      const twitchTotal = quick.viewer_count ?? 0;
      if (inChat > 0) {
        setMessage(
          `En chat: ${inChat} usuarios` +
            (twitchTotal ? ` · Twitch reporta ${twitchTotal} viewers en el stream` : ""),
        );
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Error al sincronizar");
      fullLoadInFlight.current = false;
      setLoadPhase("idle");
      return;
    }

    setLoadPhase("full");
    setMessage((prev) =>
      prev.includes("En chat:")
        ? `${prev} · ampliando con IRC (~30s)…`
        : "Cargando listado completo del chat (IRC)…",
    );
    fullLoadMutation.mutate(id);
  };

  useEffect(() => {
    if (!streamId || !token) return;
    void triggerFullLoad(streamId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when channel changes, not on token refresh
  }, [streamId, currentStream?.platform]);

  const aiScreenMutation = useMutation({
    mutationFn: () => api.streams.screenViewers(token, streamId),
    onSuccess: (res) => {
      const ti = res.twitch_insights_matched ?? 0;
      const db = res.twitch_insights_db_size ?? 0;
      setMessage(
          `${res.screened} usuarios analizados · ${res.flagged} coincidencias conocidas · ` +
            `${res.review_required ?? 0} requieren revisión` +
            (currentStream?.platform === "twitch" ? ` · ${ti} en Twitch Insights` : ""),
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["monitor-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const wekaPreviewQuery = useQuery({
    queryKey: ["weka-j48-preview", j48Source],
    queryFn: () => api.wekaJ48.preview(token, j48Source),
    enabled: !!token,
    staleTime: 60000,
  });

  const wekaTrainMutation = useMutation({
    mutationFn: () => api.wekaJ48.train(token, { source: j48Source }),
    onSuccess: (res) => {
      if (!res.ok) {
        setMessage(res.hint || res.error || "No hay suficientes datos para entrenar J48");
        return;
      }
      setMessage(
        `J48 entrenado: ${res.samples ?? 0} muestras (${res.bots ?? 0} bots / ${res.humans ?? 0} humanos) · ${(res.training as { backend?: string })?.backend ?? "?"}`,
      );
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["weka-j48-preview"] });
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
      api.streams.banSuspected(token, streamId, {
        apply_twitch_ban: currentStream?.platform === "twitch" && !currentStream.monitor_mode,
        duration_hours: 24,
      }),
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
        apply_twitch_ban: currentStream?.platform === "twitch" && !currentStream.monitor_mode,
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
  const knownBotCount = viewers.filter(
    (viewer) =>
      (viewer.behavior_metrics?.ai_verdict as { classification?: string } | undefined)
        ?.classification === "known_bot",
  ).length;
  const twitchViewers = monitorStatus?.viewer_count ?? currentStream?.viewer_count ?? 0;
  const viewersNotIdentifiable = monitorStatus?.viewers_not_identifiable ?? 0;
  const proxyIps = monitorStatus?.proxy_ips_detected ?? 0;
  const activeAttacks = monitorStatus?.active_attacks ?? 0;
  const syncing = loadPhase !== "idle" || fullLoadMutation.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="text-cyber-info" />
          Quién está viendo el stream
        </h1>
        <p className="text-cyber-muted text-sm mt-1 max-w-3xl">
          Al elegir un canal cargamos participantes observados en el chat. Las plataformas no revelan
          la identidad de quienes miran sin escribir. Viewers en vivo según {platformLabel(currentStream?.platform)}:{" "}
          <strong className="text-white">{twitchViewers || "—"}</strong>
          {monitorStatus?.active_viewers_tracked != null && twitchViewers > 0 && (
            <>
              {" "}
              · en chat: <strong className="text-cyber-accent">{totalInChat}</strong>
            </>
          )}
          {viewersNotIdentifiable > 0 && (
            <>
              {" "}· fuera del chat / no identificables: {" "}
              <strong className="text-cyber-muted">~{viewersNotIdentifiable}</strong>
            </>
          )}
            {currentStream?.platform === "twitch" && currentStream.monitor_mode && !monitorStatus?.has_broadcaster_oauth && (
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
          <Stat
            label={`${platformLabel(currentStream?.platform)} en vivo`}
            value={String(twitchViewers)}
          />
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

      {currentStream?.platform === "twitch" && currentStream.monitor_mode && !monitorStatus?.has_broadcaster_oauth && (
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

        {monitorStatus?.has_broadcaster_oauth && currentStream?.platform === "twitch" && currentStream.monitor_mode && (
        <p className="text-xs text-cyber-accent border border-cyber-accent/30 rounded-lg px-3 py-2">
          Helix conectado — la carga del listado usa la API oficial de chatters de
          Twitch.
        </p>
      )}

      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-cyber-muted block mb-1">Canal</label>
          <select
            value={streamId}
            onChange={(e) => handleStreamSelect(e.target.value)}
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
          disabled={!streamId || fullLoadMutation.isPending}
          onClick={() => triggerFullLoad(streamId, true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm disabled:opacity-50"
        >
          <Users size={16} className={syncing ? "animate-spin" : ""} />
          {syncing
            ? loadPhase === "quick"
              ? currentStream?.platform === "twitch"
                ? "Listando (Helix)…"
                : "Sincronizando chat…"
              : "Ampliando (IRC)…"
            : currentStream?.platform === "twitch"
              ? "Recargar listado"
              : "Sincronizar chat"}
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
          {aiScreenMutation.isPending ? "Analizando..." : "Analizar señales de bots"}
        </button>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={j48Source}
            onChange={(e) =>
              setJ48Source(e.target.value as "mixed" | "registered_bots" | "channel_flow")
            }
            className="bg-cyber-bg border border-cyber-border rounded-lg px-2 py-2 text-xs text-white"
            title="Fuente de datos para entrenar J48"
          >
            <option value="mixed">J48: mixto</option>
            <option value="registered_bots">J48: bases bots</option>
            <option value="channel_flow">J48: flujo canales</option>
          </select>
          <button
            type="button"
            disabled={wekaTrainMutation.isPending}
            onClick={() => wekaTrainMutation.mutate()}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-sm text-cyber-muted hover:text-white disabled:opacity-50"
            title="Entrena arbol J48 (requiere admin)"
          >
            <Brain size={16} className={wekaTrainMutation.isPending ? "animate-pulse" : ""} />
            {wekaTrainMutation.isPending ? "Entrenando..." : "Entrenar J48"}
          </button>
          {wekaPreviewQuery.data && (
            <span className="text-[10px] text-cyber-muted">
              {wekaPreviewQuery.data.rows} filas ({wekaPreviewQuery.data.bots}B/
              {wekaPreviewQuery.data.humans}H)
              {wekaPreviewQuery.data.ready ? " · listo" : " · faltan datos"}
            </span>
          )}
        </div>
        {currentStream?.platform === "twitch" && knownBotCount > 0 && (
          <button
            type="button"
            disabled={banSuspectedMutation.isPending}
            onClick={() => banSuspectedMutation.mutate()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-950/40 text-red-300 border border-red-500/40 text-sm disabled:opacity-50"
          >
            <Ban size={16} />
            {banSuspectedMutation.isPending
              ? "Baneando..."
              : `Banear bots conocidos (${knownBotCount})`}
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
              <th className="text-center py-3 px-2">J48</th>
              <th className="text-center py-3 px-2">Msgs</th>
              <th className="text-center py-3 px-2">Estado</th>
              <th className="text-right py-3 px-2">Accion</th>
            </tr>
          </thead>
          <tbody>
              {viewers.map((v) => {
                const assessment = viewerAssessment(v);
                return (
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
                <td
                  className={clsx(
                    "py-3 px-2 text-right font-mono",
                    v.risk_score >= 70
                      ? "text-cyber-danger"
                      : v.risk_score >= 40
                        ? "text-amber-400"
                        : "text-cyber-muted",
                  )}
                >
                  {v.risk_score.toFixed(0)}
                </td>
                <td className="py-3 px-2 text-center text-xs">
                  {v.j48_probability != null ? (
                    <span
                      className={clsx(
                        "font-mono",
                        v.j48_is_bot ? "text-cyber-danger" : "text-cyber-accent",
                      )}
                      title={v.j48_backend ? `Modelo: ${v.j48_backend}` : undefined}
                    >
                      {v.j48_is_bot ? "BOT probable" : "Sin señal"}{" "}
                      {(v.j48_probability * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-cyber-muted">—</span>
                  )}
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
                  <div>
                    <span className={`${assessment.tone} block`}>{assessment.label}</span>
                    <span className="text-cyber-muted text-[10px] line-clamp-2">
                      {assessment.detail}
                    </span>
                    {(v.chat_messages ?? 0) > 0 && (
                      <span className="text-cyber-muted text-[10px] block">Participa en chat</span>
                    )}
                  </div>
                </td>
                <td className="py-3 px-2 text-right">
                  {assessment.label === "Bot conocido" && currentStream?.platform === "twitch" && (
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
                );
              })}
          </tbody>
        </table>
        {!streamId && (
          <p className="text-center py-12 text-cyber-muted">
            Anade un canal en <Link href="/dashboard/channels" className="text-cyber-accent">Channels</Link>
          </p>
        )}
        {streamId && !syncing && !isLoading && viewers.length === 0 && (
          <p className="text-center py-12 text-cyber-muted">
            {!currentStream?.is_live
              ? "Canal offline o sin usuarios en chat. Si está en vivo, pulsa Recargar listado."
              : "Sin usuarios en chat — el listado se actualizará al terminar la carga."}
          </p>
        )}
        {streamId && syncing && viewers.length === 0 && (
          <p className="text-center py-12 text-cyber-muted flex items-center justify-center gap-2">
            <RefreshCw size={14} className="animate-spin" />
            Cargando listado completo de @{currentStream?.channel_name ?? "canal"}…
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
