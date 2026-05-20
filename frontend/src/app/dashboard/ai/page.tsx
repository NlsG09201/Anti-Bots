"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  AlertTriangle,
  RefreshCw,
  Sparkles,
  Shield,
  TrendingUp,
} from "lucide-react";
import { api, type AIPredictionEntry } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import clsx from "clsx";

const THREAT_COLORS: Record<string, string> = {
  low: "text-cyber-accent border-cyber-accent/40 bg-cyber-accent/10",
  medium: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
  high: "text-orange-400 border-orange-500/40 bg-orange-500/10",
  critical: "text-red-400 border-red-500/40 bg-red-500/10",
};

function PredictionCard({ entry }: { entry: AIPredictionEntry }) {
  const p = entry.prediction;
  const level = p.threat_level || "low";

  return (
    <article className="cyber-card p-4 space-y-3">
      <header className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium text-white">{entry.channel_name}</h3>
          <p className="text-xs text-cyber-muted uppercase">{entry.platform}</p>
        </div>
        <span
          className={clsx(
            "text-xs px-2 py-0.5 rounded border uppercase font-semibold",
            THREAT_COLORS[level] ?? THREAT_COLORS.low,
          )}
        >
          {level}
        </span>
      </header>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <Metric label="Risk score" value={`${p.risk_score.toFixed(0)}`} />
        <Metric label="Attack P" value={`${(p.attack_probability * 100).toFixed(0)}%`} />
        <Metric label="Viewbot P" value={`${(p.viewbot_probability * 100).toFixed(0)}%`} />
        <Metric label="Raid P" value={`${(p.raid_probability * 100).toFixed(0)}%`} />
      </div>

      {p.early_warning && (
        <p className="text-xs text-orange-300 flex items-center gap-1">
          <AlertTriangle size={14} /> Early warning — attack likely in next window
        </p>
      )}

      <p className="text-xs text-cyber-muted">
        {p.classification !== "none" && (
          <span className="text-white capitalize">{p.classification.replace("_", " ")} · </span>
        )}
        Action: <span className="text-cyber-accent">{p.recommended_action}</span>
      </p>

      {p.recommendations?.length > 0 && (
        <ul className="text-xs text-cyber-muted list-disc pl-4 space-y-0.5">
          {p.recommendations.slice(0, 2).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-cyber-border bg-cyber-bg/50 px-3 py-2">
      <p className="text-[10px] uppercase text-cyber-muted">{label}</p>
      <p className="text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

export default function AIPredictionsPage() {
  const token = useApiToken() ?? "";
  const queryClient = useQueryClient();

  const { data: health } = useQuery({
    queryKey: ["ai-health"],
    queryFn: () => api.aiIntel.health(token),
    enabled: !!token,
  });

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["ai-predictions"],
    queryFn: () => api.aiIntel.predictions(token),
    enabled: !!token,
    refetchInterval: 20000,
  });

  const trainMutation = useMutation({
    mutationFn: () => api.aiIntel.train(token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-predictions"] });
      queryClient.invalidateQueries({ queryKey: ["ai-health"] });
    },
  });

  const predictions = data?.predictions ?? [];
  const earlyWarnings = predictions.filter((e) => e.prediction.early_warning);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Brain className="text-cyber-accent" size={28} />
            AI Predictions
          </h1>
          <p className="text-cyber-muted text-sm mt-1">
            Real-time anomaly detection, attack probability, and early warnings
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            className="flex items-center gap-1 px-3 py-2 text-sm rounded-lg border border-cyber-border text-cyber-muted hover:text-white cursor-pointer"
          >
            <RefreshCw size={16} /> Refresh
          </button>
          <button
            type="button"
            disabled={trainMutation.isPending}
            onClick={() => trainMutation.mutate()}
            className="flex items-center gap-1 px-3 py-2 text-sm rounded-lg bg-cyber-accent/20 border border-cyber-accent/40 text-cyber-accent cursor-pointer disabled:opacity-50"
          >
            <Sparkles size={16} />
            {trainMutation.isPending ? "Training…" : "Retrain models"}
          </button>
        </div>
      </div>

      {health && (
        <div className="cyber-card p-4 flex flex-wrap gap-4 text-sm">
          <span className="text-cyber-muted">
            Models:{" "}
            <span className="text-white">{health.models_loaded.join(", ") || "heuristic"}</span>
          </span>
          <span className="text-cyber-muted">
            Version: <span className="text-white">{health.model_version}</span>
          </span>
          <span className="text-cyber-muted">
            Mode: <span className="text-cyber-accent">{health.mode}</span>
          </span>
        </div>
      )}

      {earlyWarnings.length > 0 && (
        <section className="rounded-lg border border-orange-500/30 bg-orange-500/5 p-4">
          <h2 className="text-sm font-medium text-orange-300 flex items-center gap-2 mb-3">
            <TrendingUp size={16} /> Early warnings ({earlyWarnings.length})
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {earlyWarnings.map((e) => (
              <PredictionCard key={e.stream_id} entry={e} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-medium text-white flex items-center gap-2 mb-4">
          <Shield size={16} className="text-cyber-accent" />
          Stream predictions
        </h2>
        {isLoading && <p className="text-cyber-muted text-sm">Loading predictions…</p>}
        {!isLoading && predictions.length === 0 && (
          <p className="text-cyber-muted text-sm">
            No cached predictions yet. Open a live stream with viewer activity to populate AI
            assessments.
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {predictions
            .filter((e) => !e.prediction.early_warning)
            .map((e) => (
              <PredictionCard key={e.stream_id} entry={e} />
            ))}
        </div>
      </section>
    </div>
  );
}
