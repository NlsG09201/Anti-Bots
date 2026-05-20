"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Binary,
  Brain,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Users,
  ExternalLink,
} from "lucide-react";
import clsx from "clsx";
import { api, type Stream, type WekaJ48Prediction } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";

type J48Source = "mixed" | "registered_bots" | "channel_flow";

function formatDate(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded border",
        ok
          ? "text-cyber-accent border-cyber-accent/40 bg-cyber-accent/10"
          : "text-cyber-muted border-cyber-border",
      )}
    >
      {label}
    </span>
  );
}

export default function WekaJ48Page() {
  const token = useApiToken() ?? "";
  const queryClient = useQueryClient();
  const [source, setSource] = useState<J48Source>("mixed");
  const [selectedStream, setSelectedStream] = useState("");
  const [message, setMessage] = useState("");

  const { data: health, refetch: refetchHealth } = useQuery({
    queryKey: ["weka-health"],
    queryFn: () => api.wekaJ48.health(token),
    enabled: !!token,
    refetchInterval: 30000,
  });

  const { data: preview, refetch: refetchPreview } = useQuery({
    queryKey: ["weka-preview", source],
    queryFn: () => api.wekaJ48.preview(token, source),
    enabled: !!token,
  });

  const { data: streams = [] } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.streams.list(token, true),
    enabled: !!token,
  });

  const streamId = selectedStream || streams[0]?.id || "";
  const currentStream = streams.find((s: Stream) => s.id === streamId);

  const {
    data: predictData,
    isLoading: predictionsLoading,
    refetch: refetchPredictions,
  } = useQuery({
    queryKey: ["weka-predictions", streamId],
    queryFn: () => api.wekaJ48.predictStream(token, streamId),
    enabled: !!token && !!streamId && !!health?.model_loaded,
    refetchInterval: 45000,
  });

  const trainMutation = useMutation({
    mutationFn: () => api.wekaJ48.train(token, { source }),
    onSuccess: (res) => {
      if (!res.ok) {
        setMessage(res.hint || res.error || "No se pudo entrenar el modelo");
        return;
      }
      setMessage(
        `Modelo entrenado: ${res.samples ?? 0} muestras (${res.bots ?? 0} bots / ${res.humans ?? 0} humanos)`,
      );
      void refetchHealth();
      void refetchPreview();
      void queryClient.invalidateQueries({ queryKey: ["weka-predictions"] });
      void queryClient.invalidateQueries({ queryKey: ["viewers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const predictions = predictData?.predictions ?? [];
  const botPredictions = useMemo(
    () =>
      [...predictions]
        .filter((p) => p.is_bot)
        .sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0)),
    [predictions],
  );
  const humanPredictions = useMemo(
    () =>
      [...predictions]
        .filter((p) => !p.is_bot)
        .sort((a, b) => (a.probability ?? 0) - (b.probability ?? 0)),
    [predictions],
  );

  const modelReady = !!health?.model_loaded;

  return (
    <div className="space-y-6 max-w-6xl">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Binary className="text-cyber-accent" size={28} />
            Weka J48 — Clasificador de bots
          </h1>
          <p className="text-sm text-cyber-muted mt-1">
            Árbol de decisión entrenado con bases de bots registradas y flujo de tus canales.
          </p>
        </div>
        <Link
          href="/dashboard/viewers"
          className="text-sm text-cyber-accent hover:underline flex items-center gap-1"
        >
          <Users size={14} /> Ver en listado Viewers
          <ExternalLink size={12} />
        </Link>
      </header>

      {message && (
        <p
          className={clsx(
            "text-sm rounded-lg px-3 py-2 border",
            message.includes("entrenado")
              ? "text-cyber-accent border-cyber-accent/30 bg-cyber-accent/5"
              : "text-orange-300 border-orange-500/30 bg-orange-500/5",
          )}
        >
          {message}
        </p>
      )}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Modelo"
          value={modelReady ? "Cargado" : "Sin entrenar"}
          ok={modelReady}
        />
        <StatCard
          label="Backend"
          value={health?.backend ?? "—"}
          ok={modelReady}
        />
        <StatCard
          label="Último entrenamiento"
          value={formatDate(health?.trained_at)}
          ok={modelReady}
          small
        />
        <StatCard
          label="Muestras (train)"
          value={health?.training_samples != null ? String(health.training_samples) : "—"}
          ok={modelReady}
        />
      </section>

      <section className="cyber-card p-4 space-y-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <Brain size={16} className="text-cyber-accent" />
          Estado del runtime
        </h2>
        <div className="flex flex-wrap gap-2">
          <StatusPill ok={!!health?.enabled} label={health?.enabled ? "ML activo" : "ML off"} />
          <StatusPill
            ok={!!health?.weka_python_available}
            label={health?.weka_python_available ? "Weka Python" : "Sin Weka Python"}
          />
          <StatusPill
            ok={!!health?.java_available}
            label={health?.java_available ? "Java OK" : "Sin Java"}
          />
          <StatusPill
            ok={!!preview?.ready}
            label={preview?.ready ? "Datos listos" : "Faltan datos"}
          />
        </div>
        {preview && (
          <p className="text-xs text-cyber-muted">
            Vista previa ({source}): {preview.rows} filas · {preview.bots} bots · {preview.humans}{" "}
            humanos
            {preview.twitch_insights_db_size != null &&
              ` · Twitch Insights: ${preview.twitch_insights_db_size} bots`}
          </p>
        )}
      </section>

      <section className="cyber-card p-4 space-y-4">
        <h2 className="text-sm font-semibold text-white">Entrenar modelo</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-cyber-muted block mb-1">Fuente de datos</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as J48Source)}
              className="bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white min-w-[200px]"
            >
              <option value="mixed">Mixto (recomendado)</option>
              <option value="registered_bots">Bases de bots registradas</option>
              <option value="channel_flow">Flujo de canales</option>
            </select>
          </div>
          <button
            type="button"
            disabled={trainMutation.isPending || !preview?.ready}
            onClick={() => trainMutation.mutate()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 text-sm disabled:opacity-50"
          >
            <RefreshCw size={16} className={trainMutation.isPending ? "animate-spin" : ""} />
            {trainMutation.isPending ? "Entrenando…" : "Entrenar J48"}
          </button>
          <button
            type="button"
            onClick={() => {
              void refetchHealth();
              void refetchPreview();
            }}
            className="text-sm text-cyber-muted hover:text-white px-3 py-2"
          >
            Actualizar estado
          </button>
        </div>
        {!preview?.ready && (
          <p className="text-xs text-orange-300 flex items-center gap-1">
            <AlertTriangle size={14} />
            Escanea canales y marca sospechosos antes de entrenar (mín. {preview?.min_required ?? 50}{" "}
            filas, 2 bots y 2 humanos).
          </p>
        )}
      </section>

      <section className="cyber-card p-4 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-sm font-semibold text-white">Predicciones por canal</h2>
          <div className="flex flex-wrap gap-2 items-end">
            <div>
              <label className="text-xs text-cyber-muted block mb-1">Canal</label>
              <select
                value={streamId}
                onChange={(e) => setSelectedStream(e.target.value)}
                className="bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white min-w-[180px]"
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
              disabled={!modelReady || !streamId || predictionsLoading}
              onClick={() => void refetchPredictions()}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-sm text-cyber-muted hover:text-white disabled:opacity-50"
            >
              <RefreshCw size={14} className={predictionsLoading ? "animate-spin" : ""} />
              Refrescar
            </button>
          </div>
        </div>

        {!modelReady && (
          <p className="text-sm text-cyber-muted flex items-center gap-2">
            <AlertTriangle size={16} className="text-orange-400" />
            Entrena el modelo para ver predicciones aquí.
          </p>
        )}

        {modelReady && predictData && (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-lg border border-cyber-border bg-cyber-bg/40 px-3 py-2">
              <p className="text-[10px] uppercase text-cyber-muted">Analizados</p>
              <p className="text-xl font-semibold text-white">{predictData.count}</p>
            </div>
            <div className="rounded-lg border border-red-500/30 bg-red-950/20 px-3 py-2">
              <p className="text-[10px] uppercase text-red-300">Predichos bot</p>
              <p className="text-xl font-semibold text-red-300">{predictData.predicted_bots}</p>
            </div>
            <div className="rounded-lg border border-cyber-accent/30 bg-cyber-accent/5 px-3 py-2">
              <p className="text-[10px] uppercase text-cyber-accent">Humanos (OK)</p>
              <p className="text-xl font-semibold text-cyber-accent">
                {predictData.count - predictData.predicted_bots}
              </p>
            </div>
          </div>
        )}

        {modelReady && currentStream && (
          <p className="text-xs text-cyber-muted">
            Canal: <span className="text-white">{currentStream.channel_name}</span>
            {currentStream.is_live ? " · en vivo" : " · offline"}
          </p>
        )}

        {modelReady && predictions.length > 0 && (
          <div className="grid md:grid-cols-2 gap-4">
            <PredictionTable
              title="Bots predichos (J48)"
              rows={botPredictions}
              variant="bot"
            />
            <PredictionTable
              title="Humanos (J48)"
              rows={humanPredictions.slice(0, 50)}
              variant="human"
            />
          </div>
        )}

        {modelReady && !predictionsLoading && predictions.length === 0 && (
          <p className="text-sm text-cyber-muted">
            No hay viewers activos en este canal. Carga el listado en{" "}
            <Link href={`/dashboard/viewers?stream=${streamId}`} className="text-cyber-accent hover:underline">
              Viewers
            </Link>
            .
          </p>
        )}
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  ok,
  small,
}: {
  label: string;
  value: string;
  ok: boolean;
  small?: boolean;
}) {
  return (
    <div className="cyber-card p-3">
      <p className="text-[10px] uppercase text-cyber-muted">{label}</p>
      <p
        className={clsx(
          "font-semibold text-white mt-1 flex items-center gap-1",
          small ? "text-xs" : "text-lg",
          ok && "text-cyber-accent",
        )}
      >
        {ok && <CheckCircle2 size={small ? 14 : 18} />}
        {value}
      </p>
    </div>
  );
}

function PredictionTable({
  title,
  rows,
  variant,
}: {
  title: string;
  rows: WekaJ48Prediction[];
  variant: "bot" | "human";
}) {
  return (
    <div className="rounded-lg border border-cyber-border overflow-hidden">
      <div
        className={clsx(
          "px-3 py-2 text-xs font-medium border-b border-cyber-border",
          variant === "bot" ? "bg-red-950/30 text-red-200" : "bg-cyber-accent/10 text-cyber-accent",
        )}
      >
        {title} ({rows.length})
      </div>
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyber-muted border-b border-cyber-border/50">
              <th className="text-left py-2 px-2">Usuario</th>
              <th className="text-right py-2 px-2">Prob. bot</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.session_id ?? r.platform_username} className="border-b border-cyber-border/30">
                <td className="py-2 px-2 text-white">{r.platform_username || "—"}</td>
                <td
                  className={clsx(
                    "py-2 px-2 text-right font-mono",
                    variant === "bot" ? "text-red-300" : "text-cyber-accent",
                  )}
                >
                  {r.probability != null ? `${(r.probability * 100).toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={2} className="py-4 text-center text-cyber-muted">
                  Ninguno
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
