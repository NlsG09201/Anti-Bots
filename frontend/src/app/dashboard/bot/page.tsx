"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Loader2, Plus, Radio, Send, ShieldCheck, Trash2 } from "lucide-react";
import { api, type KickBotCommand, type KickBotSettings, type Stream } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

const emptySettings: KickBotSettings = { enabled: false, commands: [] };

export default function KickBotPage() {
  const token = useApiToken();
  const queryClient = useQueryClient();
  const [streamId, setStreamId] = useState("");
  const [settingsOverride, setSettingsOverride] = useState<{
    streamId: string;
    settings: KickBotSettings;
  } | null>(null);
  const [commandName, setCommandName] = useState("");
  const [commandResponse, setCommandResponse] = useState("");
  const [message, setMessage] = useState("");
  const [testMessage, setTestMessage] = useState("");

  const { data: streams = [], isLoading: streamsLoading } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(token!),
    enabled: !!token,
  });
  const kickStreams = useMemo(() => streams.filter((stream: Stream) => stream.platform === "kick"), [streams]);
  const activeStreamId = streamId || kickStreams[0]?.id || "";
  const stream = kickStreams.find((item: Stream) => item.id === activeStreamId);

  const botQuery = useQuery({
    queryKey: ["kick-bot-settings", activeStreamId],
    queryFn: () => api.kick.botSettings(token!, activeStreamId),
    enabled: !!token && !!activeStreamId,
  });

  const settings = settingsOverride?.streamId === activeStreamId
    ? settingsOverride.settings
    : botQuery.data ?? emptySettings;
  const updateSettings = (updater: (current: KickBotSettings) => KickBotSettings) => {
    setSettingsOverride((current) => ({
      streamId: activeStreamId,
      settings: updater(
        current?.streamId === activeStreamId
          ? current.settings
          : botQuery.data ?? emptySettings,
      ),
    }));
  };

  const saveMutation = useMutation({
    mutationFn: () => api.kick.saveBotSettings(token!, activeStreamId, settings),
    onSuccess: (saved) => {
      setSettingsOverride({ streamId: activeStreamId, settings: saved });
      setMessage("Configuración del bot guardada.");
      queryClient.invalidateQueries({ queryKey: ["kick-bot-settings", activeStreamId] });
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const sendMutation = useMutation({
    mutationFn: () => api.kick.sendBotMessage(token!, activeStreamId, testMessage),
    onSuccess: () => {
      setTestMessage("");
      setMessage("Mensaje enviado al chat de Kick.");
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const addCommand = () => {
    const normalized = `!${commandName.trim().replace(/^!+/, "").toLowerCase()}`;
    if (normalized.length < 2 || !commandResponse.trim()) {
      setMessage("Escribe el nombre y la respuesta del comando.");
      return;
    }
    if (settings.commands.some((item) => item.command.toLowerCase() === normalized)) {
      setMessage("Ese comando ya existe.");
      return;
    }
    const command: KickBotCommand = { command: normalized, response: commandResponse.trim(), enabled: true };
    updateSettings((current) => ({ ...current, commands: [...current.commands, command] }));
    setCommandName("");
    setCommandResponse("");
    setMessage("");
  };

  const authorizeKick = async (targetStreamId?: string) => {
    if (!token) return;
    try {
      const result = await api.kick.authorize(token, targetStreamId);
      window.location.assign(result.authorization_url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo iniciar la conexión de Kick.");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-cyber-accent"><Bot size={20} /><span className="text-xs font-semibold uppercase tracking-[0.2em]">Automatización de chat</span></div>
          <h1 className="text-3xl font-bold text-white">Bot para Kick</h1>
          <p className="mt-2 max-w-2xl text-sm text-cyber-muted">Administra comandos y envía mensajes al chat del canal conectado. Kick publica estas respuestas usando la cuenta autorizada del canal.</p>
        </div>
        {stream && <span className="rounded-full border border-cyber-border px-3 py-1 text-sm text-cyber-muted">{stream.channel_name}</span>}
      </header>

      {(streamsLoading || botQuery.isLoading) && activeStreamId && <div className="flex items-center gap-2 text-cyber-muted"><Loader2 className="animate-spin" size={16} /> Cargando configuración…</div>}

      {stream && botQuery.error && (
        <section role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-5">
          <h2 className="font-semibold text-amber-100">No se pudo cargar el bot de Kick</h2>
          <p className="mt-2 text-sm text-amber-100/80">{(botQuery.error as Error).message}</p>
          <button onClick={() => authorizeKick(activeStreamId)} className="mt-4 rounded-lg border border-amber-400/50 px-4 py-2 text-sm font-semibold text-amber-100 hover:bg-amber-400/10">Volver a autorizar este canal</button>
        </section>
      )}

      {!streamsLoading && kickStreams.length === 0 && (
        <section className="rounded-xl border border-cyber-border bg-cyber-surface p-6">
          <h2 className="text-lg font-semibold text-white">Conecta un canal de Kick</h2>
          <p className="mt-2 text-sm text-cyber-muted">La conexión autoriza lectura de chat, envío de mensajes y suscripción a eventos. Se solicitará también permiso para timeout y ban desde el área Viewers.</p>
          <button onClick={() => void authorizeKick()} className="mt-4 rounded-lg bg-cyber-accent px-4 py-2 font-semibold text-black">Conectar Kick</button>
        </section>
      )}

      {kickStreams.length > 1 && (
        <label htmlFor="kick-bot-channel" className="block text-sm text-cyber-muted">Canal
          <select id="kick-bot-channel" name="channel_id" value={activeStreamId} onChange={(event) => setStreamId(event.target.value)} className="mt-2 block w-full rounded-lg border border-cyber-border bg-cyber-surface p-3 text-white">
            {kickStreams.map((item: Stream) => <option key={item.id} value={item.id}>{item.channel_name}</option>)}
          </select>
        </label>
      )}

      {stream && botQuery.data && (
        <>
          <section className="rounded-xl border border-cyber-border bg-cyber-surface p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3"><Radio className={stream.is_live ? "text-cyber-accent" : "text-cyber-muted"} /><div><h2 className="font-semibold text-white">Estado del canal</h2><p className="text-sm text-cyber-muted">{stream.is_live ? "En directo" : "Conectado"} · @{stream.channel_name}</p></div></div>
              <button onClick={() => void authorizeKick()} className="rounded-lg border border-cyber-border px-3 py-2 text-sm text-white hover:border-cyber-accent">Volver a autorizar Kick</button>
            </div>
          </section>

          <section className="space-y-5 rounded-xl border border-cyber-border bg-cyber-surface p-5">
            <div className="flex items-center justify-between gap-4">
              <div><h2 className="font-semibold text-white">Respuestas automáticas</h2><p className="mt-1 text-sm text-cyber-muted">Al activar el bot, responderá a los comandos guardados en los mensajes EventSub recibidos, usando la cuenta autorizada y con una pausa global de 5 segundos por comando.</p></div>
              <button type="button" aria-pressed={settings.enabled} onClick={() => updateSettings((current) => ({ ...current, enabled: !current.enabled }))} className={`rounded-full px-4 py-2 text-sm font-semibold ${settings.enabled ? "bg-cyber-accent text-black" : "bg-cyber-bg text-cyber-muted"}`}>{settings.enabled ? "Activado" : "Desactivado"}</button>
            </div>

            <div className="grid gap-3 md:grid-cols-[1fr_2fr_auto]">
              <label className="sr-only" htmlFor="kick-command-name">Nombre del comando</label>
              <input id="kick-command-name" name="command_name" value={commandName} onChange={(event) => setCommandName(event.target.value)} placeholder="comando (ej. discord)" className="rounded-lg border border-cyber-border bg-cyber-bg px-3 py-2 text-white placeholder:text-cyber-muted" />
              <label className="sr-only" htmlFor="kick-command-response">Respuesta del comando</label>
              <input id="kick-command-response" name="command_response" value={commandResponse} onChange={(event) => setCommandResponse(event.target.value)} placeholder="Respuesta. Puedes usar {user} y {channel}." className="rounded-lg border border-cyber-border bg-cyber-bg px-3 py-2 text-white placeholder:text-cyber-muted" />
              <button onClick={addCommand} className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyber-accent/40 px-4 py-2 text-cyber-accent"><Plus size={16} /> Añadir</button>
            </div>

            <div className="space-y-2">
              {settings.commands.map((command, index) => (
                <div key={`${command.command}-${index}`} className="flex flex-wrap items-center gap-3 rounded-lg border border-cyber-border bg-cyber-bg p-3">
                  <code className="min-w-24 text-cyber-accent">{command.command}</code>
                  <span className="min-w-40 flex-1 text-sm text-white">{command.response}</span>
                  <button onClick={() => updateSettings((current) => ({ ...current, commands: current.commands.map((item, i) => i === index ? { ...item, enabled: !item.enabled } : item) }))} className="text-xs text-cyber-muted">{command.enabled ? "Activo" : "Pausado"}</button>
                  <button aria-label={`Eliminar ${command.command}`} onClick={() => updateSettings((current) => ({ ...current, commands: current.commands.filter((_, i) => i !== index) }))} className="rounded p-2 text-red-400 hover:bg-red-400/10"><Trash2 size={16} /></button>
                </div>
              ))}
              {settings.commands.length === 0 && <p className="rounded-lg border border-dashed border-cyber-border p-5 text-center text-sm text-cyber-muted">Aún no hay comandos. Añade uno y guarda la configuración.</p>}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cyber-border pt-4">
              <div className="flex items-center gap-2 text-xs text-cyber-muted"><ShieldCheck size={15} /> No se aplican sanciones automáticas desde estos comandos.</div>
              <button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()} className="inline-flex items-center gap-2 rounded-lg bg-cyber-accent px-4 py-2 font-semibold text-black disabled:opacity-50">{saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} Guardar bot</button>
            </div>
          </section>

          <section className="rounded-xl border border-cyber-border bg-cyber-surface p-5">
            <h2 className="font-semibold text-white">Enviar mensaje</h2>
            <p className="mt-1 text-sm text-cyber-muted">Envía un mensaje al canal conectado usando la cuenta autorizada.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <label className="sr-only" htmlFor="kick-test-message">Mensaje para enviar al chat</label>
              <input id="kick-test-message" name="test_message" value={testMessage} onChange={(event) => setTestMessage(event.target.value)} maxLength={500} placeholder="Mensaje para el chat" className="min-w-60 flex-1 rounded-lg border border-cyber-border bg-cyber-bg px-3 py-2 text-white placeholder:text-cyber-muted" />
              <button disabled={!testMessage.trim() || sendMutation.isPending} onClick={() => sendMutation.mutate()} className="inline-flex items-center gap-2 rounded-lg border border-cyber-accent/40 px-4 py-2 text-cyber-accent disabled:opacity-40">{sendMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Enviar</button>
            </div>
          </section>
        </>
      )}

      {message && <p role="status" className="rounded-lg border border-cyber-border bg-cyber-surface px-4 py-3 text-sm text-white">{message}</p>}
    </div>
  );
}
