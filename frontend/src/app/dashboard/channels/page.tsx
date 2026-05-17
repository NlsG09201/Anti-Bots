"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Link2, Plus, RefreshCw, Trash2, Users, Tv, Radio } from "lucide-react";
import Link from "next/link";
import { api, type Stream } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

function ChannelsContent() {
  const searchParams = useSearchParams();
  const { accessToken } = useAuthStore();
  const token = accessToken!;
  const queryClient = useQueryClient();
  const [login, setLogin] = useState("");
  const [message, setMessage] = useState("");
  const [scanningId, setScanningId] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState("");

  useEffect(() => {
    if (searchParams.get("twitch") === "connected") {
      setMessage("Twitch del canal conectado. Ya puedes usar Helix chatters y ban en Twitch.");
      queryClient.invalidateQueries({ queryKey: ["streams"] });
    }
    const err = searchParams.get("twitch_error");
    if (err) {
      setMessage(searchParams.get("twitch_msg") || err);
    }
  }, [searchParams, queryClient]);

  const { data: streams = [], isLoading } = useQuery({
    queryKey: ["streams", "sync"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
    refetchInterval: 30000,
  });

  const watchMutation = useMutation({
    mutationFn: () => api.streams.watch(token, login.trim()),
    onSuccess: () => {
      setMessage(`Canal @${login} en monitoreo. Abre Viewers y pulsa Escanear cuando este en vivo.`);
      setLogin("");
      queryClient.invalidateQueries({ queryKey: ["streams"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const monitorMutation = useMutation({
    mutationFn: (id: string) => api.streams.monitor(token, id),
    onMutate: (id) => setScanningId(id),
    onSettled: () => setScanningId(null),
    onSuccess: (res, id) => {
      const ch = streams.find((s) => s.id === id)?.channel_name ?? "";
      setMessage(
        res.status === "offline"
          ? `${ch} esta offline`
          : `${ch}: ${res.chatters_synced ?? 0} en chat, ${res.suspected_count ?? 0} sospechosos${
              res.attack_created ? " — revisa Ataques" : ""
            }`,
      );
      queryClient.invalidateQueries({ queryKey: ["streams"] });
      queryClient.invalidateQueries({ queryKey: ["viewers"] });
      queryClient.invalidateQueries({ queryKey: ["attacks"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const unwatchMutation = useMutation({
    mutationFn: (id: string) => api.streams.unwatch(token, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["streams"] }),
  });

  const inviteMutation = useMutation({
    mutationFn: (id: string) => api.streams.channelInvite(token, id),
    onSuccess: (data) => {
      setInviteUrl(data.invite_url);
      setMessage(`Enlace listo para @${data.channel_login}. El streamer debe abrirlo e iniciar sesion con su cuenta.`);
      navigator.clipboard?.writeText(data.invite_url);
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
          Observa otros streams en vivo: chat real, sospechosos y deteccion de ataques (sin simulacion)
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyber-accent border border-cyber-accent/30 rounded-lg px-4 py-2">
          {message}
        </p>
      )}
      {inviteUrl && (
        <p className="text-xs text-cyber-muted break-all border border-cyber-border rounded-lg p-3">
          {inviteUrl}
        </p>
      )}

      <div className="cyber-card">
        <h2 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
          <Plus size={16} className="text-cyber-accent" />
          Monitorear canal de Twitch
        </h2>
        <p className="text-xs text-cyber-muted mb-4">
          Cuando el canal este LIVE, el servidor escanea el chat (~30s) y detecta picos de viewers.
          Bloqueo en canales ajenos = lista negra local; en tu canal OAuth tambien aplica en Twitch.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="login del canal, ej. ibai"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            className="flex-1 min-w-[200px] bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            disabled={!login.trim() || watchMutation.isPending}
            onClick={() => watchMutation.mutate()}
            className="px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm"
          >
            Anadir
          </button>
        </div>
      </div>

      <ChannelSection
        title="Tu canal (OAuth)"
        icon={Tv}
        empty="Conecta Twitch en Settings"
        streams={owned}
        isLoading={isLoading}
        onMonitor={(id) => monitorMutation.mutate(id)}
        scanningId={scanningId}
        showUnwatch={false}
        onUnwatch={() => {}}
      />

      <ChannelSection
        title="Canales observados"
        icon={Eye}
        empty="Anade un canal arriba"
        streams={monitored}
        isLoading={isLoading}
        onMonitor={(id) => monitorMutation.mutate(id)}
        scanningId={scanningId}
        onUnwatch={(id) => unwatchMutation.mutate(id)}
        onInvite={(id) => inviteMutation.mutate(id)}
        showUnwatch
        showInvite
      />

      <p className="text-xs text-cyber-muted">
        Canal ajeno LIVE → <strong className="text-white">Invitar streamer</strong> (listado Helix
        completo) o{" "}
        <Link href="/dashboard/viewers" className="text-cyber-accent hover:underline">
          Viewers → Cargar listado completo
        </Link>{" "}
        (IRC ~50s). Twitch no muestra viewers silenciosos, solo quien esta en chat.
      </p>
    </div>
  );
}

export default function ChannelsPage() {
  return (
    <Suspense fallback={<p className="text-cyber-muted p-6">Cargando...</p>}>
      <ChannelsContent />
    </Suspense>
  );
}

function ChannelSection({
  title,
  icon: Icon,
  empty,
  streams,
  isLoading,
  onMonitor,
  scanningId,
  onUnwatch,
  onInvite,
  showUnwatch,
  showInvite,
}: {
  title: string;
  icon: typeof Tv;
  empty: string;
  streams: Stream[];
  isLoading: boolean;
  onMonitor: (id: string) => void;
  scanningId: string | null;
  onUnwatch: (id: string) => void;
  onInvite?: (id: string) => void;
  showUnwatch: boolean;
  showInvite?: boolean;
}) {
  return (
    <div className="cyber-card">
      <h2 className="text-sm font-medium text-white mb-4 flex items-center gap-2">
        <Icon size={16} className="text-cyber-accent" />
        {title}
      </h2>
      {isLoading && <p className="text-cyber-muted text-sm">Cargando...</p>}
      {!isLoading && !streams.length && <p className="text-cyber-muted text-sm">{empty}</p>}
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
                  "offline — escaneo cuando este en vivo"
                )}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!stream.is_live || scanningId === stream.id}
                onClick={() => onMonitor(stream.id)}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-accent/40 text-cyber-accent disabled:opacity-40"
              >
                <Radio size={12} />
                {scanningId === stream.id ? "Escaneando..." : "Escanear chat"}
              </button>
              {showInvite && onInvite && stream.monitor_mode && !stream.is_owned && (
                <button
                  type="button"
                  onClick={() => onInvite(stream.id)}
                  className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-info/40 text-cyber-info hover:bg-cyber-info/10"
                  title="El streamer abre el enlace y conecta su cuenta Twitch"
                >
                  <Link2 size={12} /> Invitar streamer
                </button>
              )}
              <Link
                href={`/dashboard/viewers?stream=${stream.id}`}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-border text-cyber-muted hover:text-white"
              >
                <Users size={12} /> Listado viewers
              </Link>
              <Link
                href={`/dashboard/attacks?stream=${stream.id}`}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-border text-cyber-muted hover:text-white"
              >
                Ataques
              </Link>
              {showUnwatch && (
                <button
                  type="button"
                  onClick={() => onUnwatch(stream.id)}
                  className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-cyber-danger/40 text-cyber-danger"
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
