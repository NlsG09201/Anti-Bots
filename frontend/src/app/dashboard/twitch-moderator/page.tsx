"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, ExternalLink, Loader2, Radio, Shield, Unplug } from "lucide-react";
import { api, type Stream, type TwitchChatModerationConfig } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

const defaults: TwitchChatModerationConfig = {
  enabled: false, observe_only: true, links_enabled: false, allowed_domains: [],
  link_action: "delete", repeated_messages_enabled: true, repeat_limit: 3,
  repeat_window_seconds: 20, repeat_action: "timeout", blocked_words: [],
  word_action: "timeout", timeout_seconds: 600,
};

const fieldClass = "w-full rounded-lg border border-cyber-border bg-cyber-bg px-3 py-2 text-white";
const labelClass = "block space-y-1 text-sm text-cyber-muted";

export default function TwitchModeratorPage() {
  const token = useApiToken();
  const queryClient = useQueryClient();
  const [streamId, setStreamId] = useState("");
  const [config, setConfig] = useState<TwitchChatModerationConfig>(defaults);
  const [notice, setNotice] = useState("");

  const streamsQuery = useQuery({ queryKey: ["streams"], queryFn: () => api.streams.list(token!), enabled: !!token });
  const channels = useMemo(() => (streamsQuery.data ?? []).filter((s: Stream) => s.platform === "twitch" && s.can_manage !== false), [streamsQuery.data]);
  const activeId = streamId || channels[0]?.id || "";
  const channel = channels.find((s: Stream) => s.id === activeId);
  const query = useQuery({
    queryKey: ["twitch-chat-bot", activeId],
    queryFn: () => api.twitch.chatBotSettings(token!, activeId),
    enabled: !!token && !!activeId,
  });

  useEffect(() => {
    if (query.data) {
      const saved: TwitchChatModerationConfig = {
        enabled: query.data.enabled,
        observe_only: query.data.observe_only,
        links_enabled: query.data.links_enabled,
        allowed_domains: query.data.allowed_domains,
        link_action: query.data.link_action,
        repeated_messages_enabled: query.data.repeated_messages_enabled,
        repeat_limit: query.data.repeat_limit,
        repeat_window_seconds: query.data.repeat_window_seconds,
        repeat_action: query.data.repeat_action,
        blocked_words: query.data.blocked_words,
        word_action: query.data.word_action,
        timeout_seconds: query.data.timeout_seconds,
      };
      setConfig(saved);
    }
  }, [query.data]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const stream = params.get("stream");
    if (stream) setStreamId(stream);
    if (params.get("twitch") === "connected") setNotice("Permisos del canal actualizados. Pulsa “Añadir como moderador y activar chat”.");
    if (params.get("bot") === "connected") setNotice("Cuenta bot autorizada. Pulsa “Añadir como moderador y activar chat” para completar la configuración.");
    const error = params.get("bot_error");
    if (error) setNotice(params.get("bot_msg") || `No se pudo conectar la cuenta bot (${error}).`);
  }, []);

  const save = useMutation({
    mutationFn: () => api.twitch.saveChatBotSettings(token!, activeId, config),
    onSuccess: () => { setNotice("Reglas guardadas."); queryClient.invalidateQueries({ queryKey: ["twitch-chat-bot", activeId] }); },
    onError: (error: Error) => setNotice(error.message),
  });
  const authorize = useMutation({
    mutationFn: () => api.twitch.authorizeChatBot(token!, activeId),
    onSuccess: (result) => window.location.assign(result.authorization_url),
    onError: (error: Error) => setNotice(error.message),
  });
  const authorizeChannel = useMutation({
    mutationFn: () => api.twitch.authorize(token!, activeId, "/dashboard/twitch-moderator"),
    onSuccess: (result) => window.location.assign(result.authorization_url),
    onError: (error: Error) => setNotice(error.message),
  });
  const disconnect = useMutation({
    mutationFn: () => api.twitch.disconnectChatBot(token!, activeId),
    onSuccess: (result) => {
      setNotice(result.moderator_removed
        ? "Cuenta bot desconectada, eliminada como moderadora y reglas automáticas desactivadas."
        : "Cuenta bot desconectada y reglas automáticas desactivadas. Twitch no confirmó la eliminación del rol de moderador; puedes quitarlo manualmente en Twitch.");
      queryClient.invalidateQueries({ queryKey: ["twitch-chat-bot", activeId] });
    },
    onError: (error: Error) => setNotice(error.message),
  });
  const setupBot = useMutation({
    mutationFn: () => api.twitch.setupChatBot(token!, activeId),
    onSuccess: (result) => {
      setNotice(`@${result.bot_login} ${result.moderator_status === "already_moderator" ? "ya era moderador" : "se añadió como moderador"}; EventSub quedó activo.`);
      queryClient.invalidateQueries({ queryKey: ["twitch-chat-bot", activeId] });
    },
    onError: (error: Error) => setNotice(error.message),
  });

  const toggle = (key: "enabled" | "observe_only" | "links_enabled" | "repeated_messages_enabled") =>
    setConfig((current) => ({ ...current, [key]: !current[key] }));
  const setList = (key: "allowed_domains" | "blocked_words", value: string) =>
    setConfig((current) => ({ ...current, [key]: value.split("\n").map((item) => item.trim()).filter(Boolean) }));

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <div className="mb-2 flex items-center gap-2 text-cyber-accent"><Bot size={20} /><span className="text-xs font-semibold uppercase tracking-[0.2em]">Moderación del chat</span></div>
        <h1 className="text-3xl font-bold text-white">Bot moderador de Twitch</h1>
        <p className="mt-2 max-w-3xl text-sm text-cyber-muted">Configura reglas para mensajes de chat. El bot necesita su propia cuenta autorizada, estar como moderador del canal y recibir eventos EventSub.</p>
      </header>

      {(streamsQuery.isLoading || (activeId && query.isLoading)) && <div className="flex items-center gap-2 text-cyber-muted"><Loader2 size={16} className="animate-spin" /> Cargando…</div>}
      {!streamsQuery.isLoading && channels.length === 0 && <section className="rounded-xl border border-cyber-border bg-cyber-surface p-5 text-sm text-cyber-muted">No hay canales Twitch que puedas administrar. Conecta primero tu canal propietario en Canales.</section>}
      {channels.length > 1 && <label className={labelClass}>Canal Twitch<select className={`${fieldClass} mt-1`} value={activeId} onChange={(event) => setStreamId(event.target.value)}>{channels.map((item: Stream) => <option key={item.id} value={item.id}>{item.channel_name}</option>)}</select></label>}
      {query.error && <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-200">No se pudo cargar la configuración: {(query.error as Error).message}</p>}

      {channel && query.data && <>
        <section className="space-y-4 rounded-xl border border-cyber-border bg-cyber-surface p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3"><Radio className="text-cyber-accent" /><div><h2 className="font-semibold text-white">{query.data.channel_name}</h2><p className="text-sm text-cyber-muted">Canal propietario: {query.data.oauth_connected ? "conectado" : "desconectado"}</p></div></div>
            <div className="flex flex-wrap gap-2">
              <span className={`rounded-full border px-3 py-1 text-xs ${query.data.bot_connected ? "border-cyber-accent/50 text-cyber-accent" : "border-cyber-border text-cyber-muted"}`}>{query.data.bot_connected ? `Bot @${query.data.bot_login}` : "Bot sin conectar"}</span>
              {query.data.bot_connected && <span className="rounded-full border border-cyber-border px-3 py-1 text-xs text-cyber-muted">Moderador: {query.data.bot_moderator_status}</span>}
              <span className="rounded-full border border-cyber-border px-3 py-1 text-xs text-cyber-muted">EventSub: {query.data.eventsub_status}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button disabled={authorize.isPending || !query.data.oauth_connected} onClick={() => authorize.mutate()} className="inline-flex items-center gap-2 rounded-lg bg-cyber-accent px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"><ExternalLink size={16} />{query.data.bot_connected ? "Reconectar cuenta bot" : "Conectar cuenta bot"}</button>
            {notice.includes("channel:manage:moderators") && <button disabled={authorizeChannel.isPending} onClick={() => authorizeChannel.mutate()} className="inline-flex items-center gap-2 rounded-lg border border-yellow-500/40 px-4 py-2 text-sm text-yellow-100 disabled:opacity-50">{authorizeChannel.isPending && <Loader2 size={16} className="animate-spin" />}Actualizar permisos del canal</button>}
            {query.data.bot_connected && <button disabled={setupBot.isPending} onClick={() => setupBot.mutate()} className="inline-flex items-center gap-2 rounded-lg border border-cyber-border px-4 py-2 text-sm text-white disabled:opacity-50">{setupBot.isPending ? <Loader2 size={16} className="animate-spin" /> : <Radio size={16} />}Añadir como moderador y activar chat</button>}
            {query.data.bot_connected && <button disabled={disconnect.isPending} onClick={() => disconnect.mutate()} className="inline-flex items-center gap-2 rounded-lg border border-red-500/40 px-4 py-2 text-sm text-red-300 disabled:opacity-50"><Unplug size={16} />Desconectar bot</button>}
          </div>
          {query.data.bot_connected && <p className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm text-yellow-100">La aplicación añadirá <code>@{query.data.bot_login}</code> como moderador usando el permiso OAuth del canal propietario y después activará EventSub. Puede que Twitch te pida volver a autorizar el canal si ese permiso aún no fue concedido. Las reglas de sanción siguen apagadas hasta que las actives.</p>}
        </section>

        <section className="space-y-5 rounded-xl border border-cyber-border bg-cyber-surface p-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold text-white">Reglas automáticas</h2><p className="mt-1 text-sm text-cyber-muted">Empieza en modo observación para revisar coincidencias sin sancionar.</p></div><button type="button" aria-pressed={config.enabled} onClick={() => toggle("enabled")} className={`rounded-full px-4 py-2 text-sm font-semibold ${config.enabled ? "bg-cyber-accent text-black" : "bg-cyber-bg text-cyber-muted"}`}>{config.enabled ? "Reglas activadas" : "Reglas desactivadas"}</button></div>
          <label className="flex items-center gap-3 text-sm text-white"><input type="checkbox" checked={config.observe_only} onChange={() => toggle("observe_only")} />Solo observar; no borrar mensajes ni sancionar</label>
          {!query.data.bot_connected && <p className="text-sm text-yellow-200">Conecta primero una cuenta bot para guardar la activación.</p>}

          <div className="grid gap-5 md:grid-cols-2">
            <fieldset className="space-y-3 rounded-lg border border-cyber-border p-4"><legend className="px-1 font-medium text-white">Mensajes repetidos</legend>
              <label className="flex items-center gap-2 text-sm text-cyber-muted"><input type="checkbox" checked={config.repeated_messages_enabled} onChange={() => toggle("repeated_messages_enabled")} />Detectar mensajes consecutivos repetidos</label>
              <label className={labelClass}>Umbral<select className={fieldClass} value={config.repeat_limit} onChange={(e) => setConfig({ ...config, repeat_limit: Number(e.target.value) })}>{[2,3,4,5,6].map((n) => <option key={n} value={n}>{n} mensajes</option>)}</select></label>
              <label className={labelClass}>Ventana (segundos)<input className={fieldClass} type="number" min={5} max={300} value={config.repeat_window_seconds} onChange={(e) => setConfig({ ...config, repeat_window_seconds: Number(e.target.value) })} /></label>
              <ActionSelect label="Acción" value={config.repeat_action} onChange={(value) => setConfig({ ...config, repeat_action: value as "timeout" | "ban" })} timeoutAllowed />
            </fieldset>
            <fieldset className="space-y-3 rounded-lg border border-cyber-border p-4"><legend className="px-1 font-medium text-white">Enlaces</legend>
              <label className="flex items-center gap-2 text-sm text-cyber-muted"><input type="checkbox" checked={config.links_enabled} onChange={() => toggle("links_enabled")} />Detectar enlaces</label>
              <label className={labelClass}>Dominios permitidos (uno por línea)<textarea className={fieldClass} rows={4} value={config.allowed_domains.join("\n")} onChange={(e) => setList("allowed_domains", e.target.value)} placeholder="twitch.tv&#10;youtube.com" /></label>
              <ActionSelect label="Acción" value={config.link_action} onChange={(value) => setConfig({ ...config, link_action: value })} />
            </fieldset>
            <fieldset className="space-y-3 rounded-lg border border-cyber-border p-4"><legend className="px-1 font-medium text-white">Palabras bloqueadas</legend>
              <label className={labelClass}>Una palabra o frase por línea<textarea className={fieldClass} rows={6} value={config.blocked_words.join("\n")} onChange={(e) => setList("blocked_words", e.target.value)} placeholder="Añade solo términos que realmente quieras filtrar" /></label>
              <ActionSelect label="Acción" value={config.word_action} onChange={(value) => setConfig({ ...config, word_action: value })} />
            </fieldset>
            <fieldset className="space-y-3 rounded-lg border border-cyber-border p-4"><legend className="px-1 font-medium text-white">Timeout</legend>
              <label className={labelClass}>Duración<select className={fieldClass} value={config.timeout_seconds} onChange={(e) => setConfig({ ...config, timeout_seconds: Number(e.target.value) })}>{[60,300,600,1800,3600,86400,1209600].map((seconds) => <option key={seconds} value={seconds}>{seconds < 3600 ? `${seconds / 60} min` : seconds < 86400 ? `${seconds / 3600} h` : `${seconds / 86400} días`}</option>)}</select></label>
              <p className="text-xs text-cyber-muted">El ban permanente solo se aplica si seleccionas “Ban” como acción. Los términos no interpretan contexto, ironía ni conversaciones legítimas.</p>
            </fieldset>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cyber-border pt-4"><p className="flex items-center gap-2 text-xs text-cyber-muted"><Shield size={15} /> AutoMod de Twitch puede seguir habilitado en paralelo.</p><button disabled={save.isPending || !query.data.bot_connected} onClick={() => save.mutate()} className="inline-flex items-center gap-2 rounded-lg bg-cyber-accent px-4 py-2 font-semibold text-black disabled:opacity-50">{save.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}Guardar reglas</button></div>
        </section>
      </>}
      {notice && <p role="status" className="rounded-lg border border-cyber-border bg-cyber-surface px-4 py-3 text-sm text-white">{notice}</p>}
    </main>
  );
}

function ActionSelect({ label, value, onChange, timeoutAllowed = false }: { label: string; value: "delete" | "timeout" | "ban"; onChange: (value: "delete" | "timeout" | "ban") => void; timeoutAllowed?: boolean }) {
  return <label className={labelClass}>{label}<select className={fieldClass} value={value} onChange={(e) => onChange(e.target.value as "delete" | "timeout" | "ban")}>{!timeoutAllowed && <option value="delete">Borrar mensaje</option>}<option value="timeout">Timeout</option><option value="ban">Ban permanente</option></select></label>;
}
