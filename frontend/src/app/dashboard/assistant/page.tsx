"use client";

import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, Send, ShieldCheck, UserRound } from "lucide-react";
import { api, type Stream } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

type Message = { role: "user" | "assistant"; content: string };

const INITIAL_MESSAGE: Message = {
  role: "assistant",
  content:
    "Soy el asistente SOC de StreamShield. Puedo ayudarte a interpretar señales de viewbotting, spam, huellas, riesgo y mitigación.",
};

export default function AssistantPage() {
  const token = useApiToken();
  const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [streamId, setStreamId] = useState("");
  const [moderationMode, setModerationMode] = useState<"monitor" | "assisted" | "automatic">("monitor");
  const queryClient = useQueryClient();
  const streamsQuery = useQuery({
    queryKey: ["assistant-streams"],
    queryFn: () => api.streams.list(token!),
    enabled: !!token,
  });
  const usageQuery = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api.ai.usage(token!),
    enabled: !!token,
  });
  const modeQuery = useQuery({
    queryKey: ["ai-moderation-mode", streamId],
    queryFn: () => api.ai.moderationMode(token!, streamId),
    enabled: !!token && !!streamId,
  });
  const streams = (streamsQuery.data ?? []) as Stream[];
  useEffect(() => {
    if (modeQuery.data) setModerationMode(modeQuery.data.mode);
  }, [modeQuery.data]);
  const modeMutation = useMutation({
    mutationFn: () => api.ai.setModerationMode(token!, streamId, moderationMode),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-moderation-mode", streamId] }),
    onError: (err: Error) => setError(err.message),
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading || !token) return;
    const previous = messages.slice(-6);
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setError("");
    setLoading(true);
    try {
      const response = await api.assistant.chat(token, {
        message: text,
        history: previous,
        ...(streamId ? { stream_id: streamId } : {}),
      });
      setMessages((current) => [...current, { role: "assistant", content: response.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible consultar al asistente.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="cyber-card p-5">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
          <Bot className="text-cyber-accent" /> Asistente SOC
        </h1>
        <p className="mt-2 text-sm text-cyber-muted">
          Orientación para investigar amenazas de bots. No ejecuta bloqueos ni sustituye la revisión humana.
        </p>
      </header>

      <section className="cyber-card flex flex-wrap items-center justify-between gap-4 p-4">
        <label className="min-w-64 flex-1 text-sm text-cyber-muted" htmlFor="assistant-stream">
          Contexto de canal
          <select
            id="assistant-stream"
            value={streamId}
            onChange={(event) => setStreamId(event.target.value)}
            className="mt-2 block w-full rounded-lg border border-cyber-border bg-cyber-bg p-2 text-white"
          >
            <option value="">Sin datos de canal</option>
            {streams.map((stream) => (
              <option key={stream.id} value={stream.id}>
                {stream.channel_name} · {stream.platform}
              </option>
            ))}
          </select>
        </label>
        {streamId && modeQuery.data?.can_manage && (
          <label className="text-sm text-cyber-muted" htmlFor="ai-moderation-mode">
            Modo de moderación asistida
            <div className="mt-2 flex gap-2">
              <select
                id="ai-moderation-mode"
                value={moderationMode}
                onChange={(event) => setModerationMode(event.target.value as typeof moderationMode)}
                className="rounded-lg border border-cyber-border bg-cyber-bg p-2 text-white"
              >
                <option value="monitor">Monitoreo</option>
                <option value="assisted">Asistido</option>
                <option value="automatic" disabled={!modeQuery.data.automatic_available}>Automático (reglas locales)</option>
              </select>
              <button
                type="button"
                onClick={() => modeMutation.mutate()}
                disabled={modeMutation.isPending || moderationMode === "automatic" && !modeQuery.data.automatic_available}
                className="rounded-lg bg-cyber-accent/20 px-3 py-2 text-cyber-accent disabled:opacity-50"
              >Guardar</button>
            </div>
          </label>
        )}
        <div className="text-sm text-cyber-muted" aria-live="polite">
          {usageQuery.data ? (
            <>
              <strong className="text-white">Uso IA · últimos {usageQuery.data.days} días</strong>
              <div>{usageQuery.data.request_count} solicitudes · {(usageQuery.data.input_tokens + usageQuery.data.output_tokens).toLocaleString()} tokens</div>
              <div>
                {usageQuery.data.cost_estimation_configured
                  ? `Costo estimado: $${(usageQuery.data.estimated_cost_usd ?? 0).toFixed(4)} USD`
                  : "Configura precios por token para estimar costos"}
                {usageQuery.data.openai_configured ? " · OpenAI activo" : " · OpenAI no configurado"}
              </div>
            </>
          ) : "Uso IA no disponible"}
        </div>
      </section>

      <section className="cyber-card min-h-[420px] p-4">
        <div className="space-y-4">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}>
              {message.role === "assistant" && <Bot className="mt-1 shrink-0 text-cyber-accent" size={18} />}
              <p className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-cyber-accent/15 text-white" : "border border-cyber-border bg-cyber-bg/60 text-cyber-muted"}`}>
                {message.content}
              </p>
              {message.role === "user" && <UserRound className="mt-1 shrink-0 text-white" size={18} />}
            </article>
          ))}
          {loading && <p className="flex items-center gap-2 text-sm text-cyber-muted"><Loader2 className="animate-spin" size={16} /> Analizando consulta…</p>}
        </div>
      </section>

      {error && <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}

      <form onSubmit={submit} className="cyber-card flex gap-3 p-3">
        <label className="sr-only" htmlFor="assistant-question">Consulta para el asistente</label>
        <input
          id="assistant-question"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          maxLength={1000}
          placeholder="Ej.: ¿Qué señales confirman un posible viewbot?"
          className="min-w-0 flex-1 rounded-lg border border-cyber-border bg-cyber-bg px-4 py-2 text-sm text-white outline-none focus:border-cyber-accent"
        />
        <button type="submit" disabled={!input.trim() || loading || !token} className="flex items-center gap-2 rounded-lg bg-cyber-accent/20 px-4 py-2 text-sm text-cyber-accent disabled:opacity-50">
          <Send size={16} /> Enviar
        </button>
      </form>
      <p className="flex items-center gap-2 text-xs text-cyber-muted"><ShieldCheck size={14} /> Requiere sesión con rol de analista o superior; el historial queda en el navegador durante esta sesión.</p>
    </div>
  );
}
