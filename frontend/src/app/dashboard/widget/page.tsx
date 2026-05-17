"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Code, Copy, RefreshCw, Radio } from "lucide-react";
import { api, type Stream } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { resolveApiBaseUrl } from "@/lib/runtime-urls";

export default function WidgetPage() {
  const { accessToken } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();
  const [streamId, setStreamId] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
  });

  const selectedId = streamId || streams[0]?.id || "";

  const { data: embed, isLoading } = useQuery({
    queryKey: ["widget-embed", selectedId],
    queryFn: () => api.streams.widgetEmbed(token, selectedId),
    enabled: !!token && !!selectedId,
  });

  const regenKey = useMutation({
    mutationFn: () => api.streams.widgetRegenerateKey(token, selectedId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["widget-embed", selectedId] });
    },
  });

  const apiDefault = resolveApiBaseUrl() || "https://anti-bots.onrender.com";
  const scriptUrl =
    embed?.script_url ||
    (typeof window !== "undefined"
      ? `${window.location.origin}/streamshield-widget.js`
      : "https://anti-bots.vercel.app/streamshield-widget.js");

  async function copyText(label: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Code className="text-cyber-accent" />
          Widget de ingest (IP + proxy)
        </h1>
        <p className="text-cyber-muted text-sm mt-2">
          Embebe este script en tu web del canal, extension o fuente de navegador OBS. Cada visita
          envia su IP al API (via cabeceras del proxy) y un fingerprint del navegador para detectar
          VPN, proxy, TOR y bots.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-cyber-muted block mb-1">Canal</label>
          <select
            value={selectedId}
            onChange={(e) => setStreamId(e.target.value)}
            className="bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white min-w-[220px]"
          >
            {streams.map((s: Stream) => (
              <option key={s.id} value={s.id}>
                {s.channel_name}
                {s.is_live ? " LIVE" : ""}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          disabled={!selectedId || regenKey.isPending}
          onClick={() => regenKey.mutate()}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-cyber-border rounded-lg text-cyber-muted hover:text-white"
        >
          <RefreshCw size={14} className={regenKey.isPending ? "animate-spin" : ""} />
          Regenerar clave
        </button>
      </div>

      {isLoading && <p className="text-cyber-muted text-sm">Cargando configuracion...</p>}

      {embed && (
        <>
          <div className="cyber-card p-4 space-y-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Radio size={16} className="text-cyber-accent" />
              Snippet para web / extension
            </h2>
            <pre className="text-xs text-cyber-accent bg-cyber-bg p-3 rounded-lg overflow-x-auto whitespace-pre-wrap break-all">
              {embed.embed_html}
            </pre>
            <button
              type="button"
              onClick={() => copyText("embed", embed.embed_html)}
              className="text-xs flex items-center gap-1 text-cyber-accent"
            >
              <Copy size={12} />
              {copied === "embed" ? "Copiado" : "Copiar snippet"}
            </button>
          </div>

          <div className="cyber-card p-4 space-y-3">
            <h2 className="text-sm font-semibold text-white">OBS — Browser Source</h2>
            <p className="text-xs text-cyber-muted">
              Crea una fuente Navegador, pega este HTML, ancho/alto 400×300 (transparente). Deja la
              fuente visible solo si quieres pings desde OBS; en produccion suele ir en una pagina
              de panel que abren los viewers.
            </p>
            <pre className="text-xs text-cyber-muted bg-cyber-bg p-3 rounded-lg overflow-x-auto max-h-40 whitespace-pre-wrap">
              {embed.obs_browser_source_html}
            </pre>
            <button
              type="button"
              onClick={() => copyText("obs", embed.obs_browser_source_html)}
              className="text-xs flex items-center gap-1 text-cyber-accent"
            >
              <Copy size={12} />
              {copied === "obs" ? "Copiado" : "Copiar HTML OBS"}
            </button>
          </div>

          <div className="cyber-card p-4 text-sm text-cyber-muted space-y-2">
            <p>
              <span className="text-white">API:</span> {embed.api_url || apiDefault}
            </p>
            <p>
              <span className="text-white">Script:</span> {scriptUrl}
            </p>
            <p>
              <span className="text-white">Clave:</span>{" "}
              <code className="text-cyber-accent">{embed.ingest_key}</code>
            </p>
            <ul className="list-disc list-inside text-xs space-y-1 mt-2">
              {embed.instructions.map((line) => (
                <li key={line}>{line}</li>
              ))}
              <li>
                Atributo opcional:{" "}
                <code className="text-cyber-accent">data-username=&quot;twitch_login&quot;</code>
              </li>
              <li>
                Los eventos aparecen en Viewers e IPs sospechosas; ataques proxy se mitigan desde
                Ataques.
              </li>
            </ul>
          </div>
        </>
      )}

      {!streams.length && (
        <p className="text-cyber-muted text-sm">
          Anade un canal en Channels antes de generar el widget.
        </p>
      )}
    </div>
  );
}
