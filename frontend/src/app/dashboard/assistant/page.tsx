"use client";

import { FormEvent, useState } from "react";
import { Bot, Loader2, Send, ShieldCheck, UserRound } from "lucide-react";
import { api } from "@/lib/api";
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
      const response = await api.assistant.chat(token, { message: text, history: previous });
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
