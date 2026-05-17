"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Plus, RefreshCw, Trash2, Zap, Tv } from "lucide-react";
import Link from "next/link";
import { api, type Stream } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

export default function ChannelsPage() {
  const { accessToken } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();
  const [login, setLogin] = useState("");
  const [message, setMessage] = useState("");

  const { data: streams = [], isLoading } = useQuery({
    queryKey: ["streams", "sync"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
    refetchInterval: 30000,
  });

  const watchMutation = useMutation({
    mutationFn: () => api.streams.watch(token, login.trim()),
    onSuccess: () => {
      setMessage(`Canal @${login} anadido en modo monitoreo`);
      setLogin("");
      queryClient.invalidateQueries({ queryKey: ["streams"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const syncMutation = useMutation({
    mutationFn: (id: string) => api.streams.sync(token, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["streams"] }),
  });

  const unwatchMutation = useMutation({
    mutationFn: (id: string) => api.streams.unwatch(token, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["streams"] }),
  });

  const simulateMutation = useMutation({
    mutationFn: (stream: Stream) =>
      api.streams.ingestEvent(token, stream.id, {
        event_type: "viewer_join",
        platform_username: `test_bot_${Date.now() % 1000}`,
        ip_address: `203.0.113.${Math.floor(Math.random() * 200) + 1}`,
        fingerprint_hash: `fp_${Date.now().toString(16)}`,
        metadata: { fingerprint_risk: 55 + Math.random() * 30, simulated: true },
      }),
    onSuccess: (res) => {
      setMessage(
        res.attack_created
          ? "Evento simulado: ataque detectado (revisa el dashboard)"
          : `Evento simulado: riesgo ${res.risk_score.toFixed(0)}`,
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-charts"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const owned = streams.filter((s) => !s.monitor_mode);
  const monitored = streams.filter((s) => s.monitor_mode);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Canales</h1>
        <p className="text-cyber-muted text-sm mt-1">
          Tu canal (OAuth) y otros canales en modo observacion para pruebas reales
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyber-accent border border-cyber-accent/30 rounded-lg px-4 py-2">
          {message}
        </p>
      )}

      <div className="cyber-card">
        <h2 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
          <Plus size={16} className="text-cyber-accent" />
          Monitorear otro canal (Twitch)
        </h2>
        <p className="text-xs text-cyber-muted mb-4">
          Solo lectura via API publica: viewers en vivo, deteccion y simulacion. No se banea en Twitch ajeno.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="nombre del canal, ej. xqc"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            className="flex-1 min-w-[200px] bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            disabled={!login.trim() || watchMutation.isPending}
            onClick={() => watchMutation.mutate()}
            className="px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm hover:bg-cyber-accent/30 disabled:opacity-50"
          >
            Anadir observacion
          </button>
        </div>
      </div>

      <ChannelSection
        title="Tu canal (OAuth)"
        icon={Tv}
        empty="Conecta Twitch en Settings"
        streams={owned}
        isLoading={isLoading}
        onSync={(id) => syncMutation.mutate(id)}
        onSimulate={(s) => simulateMutation.mutate(s)}
        showUnwatch={false}
      />

      <ChannelSection
        title="Canales en observacion"
        icon={Eye}
        empty="Anade un login de Twitch arriba para probar con streams reales"
        streams={monitored}
        isLoading={isLoading}
        onSync={(id) => syncMutation.mutate(id)}
        onSimulate={(s) => simulateMutation.mutate(s)}
        onUnwatch={(id) => unwatchMutation.mutate(id)}
        showUnwatch
      />

      <p className="text-xs text-cyber-muted">
        Tip: tras simular eventos, el{" "}
        <Link href="/dashboard" className="text-cyber-accent hover:underline">
          dashboard
        </Link>{" "}
        actualiza graficas en tiempo real. Para IA avanzada, configura OPENAI_API_KEY en Render.
      </p>
    </div>
  );
}

function ChannelSection({
  title,
  icon: Icon,
  empty,
  streams,
  isLoading,
  onSync,
  onSimulate,
  onUnwatch,
  showUnwatch,
}: {
  title: string;
  icon: typeof Tv;
  empty: string;
  streams: Stream[];
  isLoading: boolean;
  onSync: (id: string) => void;
  onSimulate: (s: Stream) => void;
  onUnwatch?: (id: string) => void;
  showUnwatch: boolean;
}) {
  return (
    <div className="cyber-card">
      <h2 className="text-sm font-medium text-white mb-4 flex items-center gap-2">
        <Icon size={16} className="text-cyber-accent" />
        {title}
      </h2>
      {isLoading && <p className="text-cyber-muted text-sm">Cargando...</p>}
      {!isLoading && !streams.length && (
        <p className="text-cyber-muted text-sm">{empty}</p>
      )}
      <ul className="space-y-3">
        {streams.map((stream) => (
          <li
            key={stream.id}
            className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-cyber-border bg-cyber-bg/40"
          >
            <div>
              <p className="text-white font-medium">{stream.channel_name}</p>
              <p className="text-xs text-cyber-muted">
                @{stream.login || stream.channel_name.toLowerCase()} ·{" "}
                {stream.is_live ? (
                  <span className="text-cyber-accent">{stream.viewer_count} viewers LIVE</span>
                ) : (
                  "offline"
                )}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onSync(stream.id)}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-border text-cyber-muted hover:text-white"
              >
                <RefreshCw size={12} /> Sync
              </button>
              <button
                type="button"
                onClick={() => onSimulate(stream)}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-accent/40 text-cyber-accent hover:bg-cyber-accent/10"
              >
                <Zap size={12} /> Simular evento
              </button>
              <Link
                href={`/dashboard/attacks?stream=${stream.id}`}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-border text-cyber-muted hover:text-white"
              >
                Ataques
              </Link>
              {showUnwatch && onUnwatch && (
                <button
                  type="button"
                  onClick={() => onUnwatch(stream.id)}
                  className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-danger/40 text-cyber-danger hover:bg-cyber-danger/10"
                >
                  <Trash2 size={12} /> Quitar
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
