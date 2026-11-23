"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, Calculator, Clock3, ShieldAlert } from "lucide-react";
import { api, type ReviewOptimizationInput } from "@/lib/api";
import { useApiToken } from "@/stores/authStore";
import { Button } from "@/components/ui/button";

export default function OperationsResearchPage() {
  const token = useApiToken();
  const [capacity, setCapacity] = useState(60);
  const [minutes, setMinutes] = useState(5);
  const [budget, setBudget] = useState(50);
  const [cost, setCost] = useState(1);
  const [streamId, setStreamId] = useState("");
  const streams = useQuery({
    queryKey: ["streams", token],
    queryFn: () => api.streams.list(token!),
    enabled: !!token,
  });
  const initialCalculation = useQuery({
    queryKey: ["operations-research-initial", token],
    queryFn: () => api.operationsResearch.optimizeReviewQueue(token!, {
      capacity_minutes: 60,
      minutes_per_review: 5,
      false_positive_budget: 50,
      false_positive_cost: 1,
      max_candidates: 500,
    }),
    enabled: !!token,
    retry: false,
  });
  const solve = useMutation({
    mutationFn: (input: ReviewOptimizationInput) => api.operationsResearch.optimizeReviewQueue(token!, input),
  });
  const result = solve.data ?? initialCalculation.data;
  const calculationError = solve.isError
    ? solve.error
    : solve.data
      ? null
      : initialCalculation.error;
  const isCalculating = solve.isPending || initialCalculation.isPending;

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    solve.mutate({
      capacity_minutes: capacity,
      minutes_per_review: minutes,
      false_positive_budget: budget,
      false_positive_cost: cost,
      stream_id: streamId || undefined,
      max_candidates: 500,
    });
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
      <header>
        <div className="flex items-center gap-3">
          <Calculator className="h-7 w-7 text-cyber-accent" />
          <h1 className="text-2xl font-semibold text-white">Investigación de Operaciones</h1>
        </div>
        <p className="mt-2 max-w-3xl text-sm text-cyber-muted">
          Optimiza la cola de revisión con sesiones sospechosas activas de tus canales. El resultado es una recomendación para analistas; no aplica bloqueos.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-4 rounded-xl border border-cyber-border/70 bg-cyber-surface/50 p-5 md:grid-cols-5">
        <label className="text-xs text-cyber-muted">Capacidad (minutos)
          <input aria-label="Capacidad en minutos" type="number" min={1} max={1440} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} className="mt-2 w-full rounded-md border border-cyber-border bg-cyber-bg px-3 py-2 text-sm text-white" />
        </label>
        <label className="text-xs text-cyber-muted">Minutos por revisión
          <input aria-label="Minutos por revisión" type="number" min={1} max={120} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="mt-2 w-full rounded-md border border-cyber-border bg-cyber-bg px-3 py-2 text-sm text-white" />
        </label>
        <label className="text-xs text-cyber-muted">Presupuesto de exposición (0–100)
          <input aria-label="Presupuesto de exposición" type="number" min={0} max={100} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="mt-2 w-full rounded-md border border-cyber-border bg-cyber-bg px-3 py-2 text-sm text-white" />
        </label>
        <label className="text-xs text-cyber-muted">Costo relativo de falso positivo
          <input aria-label="Costo relativo de falso positivo" type="number" min={0} max={10} step={0.1} value={cost} onChange={(e) => setCost(Number(e.target.value))} className="mt-2 w-full rounded-md border border-cyber-border bg-cyber-bg px-3 py-2 text-sm text-white" />
        </label>
        <label className="text-xs text-cyber-muted">Canal
          <select aria-label="Canal" value={streamId} onChange={(e) => setStreamId(e.target.value)} className="mt-2 w-full rounded-md border border-cyber-border bg-cyber-bg px-3 py-2 text-sm text-white">
            <option value="">Todos mis canales</option>
            {(streams.data ?? []).map((stream) => <option key={stream.id} value={stream.id}>{stream.channel_name} · {stream.platform}</option>)}
          </select>
        </label>
        <div className="md:col-span-5">
          <Button disabled={isCalculating || !token}>
            <Activity className="h-4 w-4" /> {isCalculating ? "Calculando…" : "Resolver con sesiones reales"}
          </Button>
        </div>
      </form>

      {calculationError && <p role="alert" className="rounded-lg border border-cyber-danger/40 p-4 text-sm text-cyber-danger">No fue posible calcular la cola: {calculationError.message}</p>}
      {isCalculating && <p role="status" className="rounded-lg border border-cyber-border/60 p-4 text-sm text-cyber-muted">Consultando sesiones reales y resolviendo la cola de revisión…</p>}
      {result && <section aria-live="polite" className="space-y-4">
        <div role="status" className="rounded-lg border border-cyber-accent/30 bg-cyber-accent/5 p-4 text-sm text-white">
          <p className="text-[10px] uppercase tracking-wider text-cyber-accent">Recomendación calculada</p>
          <p className="mt-1">{result.recommendation}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ["Candidatas reales", result.candidate_count],
            ["Elegibles por restricciones", result.eligible_count],
            ["Sesiones seleccionadas", result.selected_count],
            ["Tiempo usado", `${result.used_minutes} / ${result.capacity_minutes} min`],
            ["Exposición estimada", `${result.estimated_exposure_points} / ${result.false_positive_budget} pts`],
          ].map(([label, value]) => <div key={label} className="rounded-lg border border-cyber-border/60 bg-cyber-bg/40 p-4"><p className="text-[10px] uppercase tracking-wider text-cyber-muted">{label}</p><p className="mt-1 text-xl font-mono text-white">{value}</p></div>)}
        </div>
        {result.candidate_count === 0 && <p role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200">No hay sesiones activas con señales de riesgo para este tenant. Verifica que los canales estén recibiendo eventos y actividad de chat.</p>}
        {result.candidate_count > 0 && result.eligible_count === 0 && <p role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200">Hay sesiones sospechosas, pero ninguna cumple el presupuesto de exposición y el costo configurados. Aumenta el presupuesto o reduce el costo relativo.</p>}
        {result.eligible_count > 0 && result.selected_count === 0 && <p role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200">Hay sesiones elegibles, pero la capacidad no alcanza para revisar ninguna con el tiempo asignado. Aumenta la capacidad o reduce los minutos por revisión.</p>}
        <div className="overflow-x-auto rounded-xl border border-cyber-border/70">
          <table className="w-full text-left text-sm"><thead className="bg-cyber-surface text-xs text-cyber-muted"><tr><th className="p-3">Orden</th><th className="p-3">Canal</th><th className="p-3">Usuario</th><th className="p-3">Riesgo observado</th><th className="p-3">Prioridad proxy</th></tr></thead>
            <tbody>{result.selected.map((row, index) => <tr key={row.session_id} className="border-t border-cyber-border/50 text-white"><td className="p-3">{index + 1}</td><td className="p-3">{row.stream_name}</td><td className="p-3">{row.username}</td><td className="p-3">{row.risk_score}/100</td><td className="p-3">{(row.priority_proxy * 100).toFixed(1)}%</td></tr>)}
              {result.selected.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-cyber-muted">No hay sesiones seleccionadas para los parámetros actuales.</td></tr>}
            </tbody></table>
        </div>
        {result.truncated && <p className="text-xs text-amber-400">La consulta alcanzó el límite de 500 candidatas; el resultado cubre las 500 de mayor riesgo.</p>}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-xs text-cyber-muted">
          <p className="mb-2 flex items-center gap-2 font-semibold text-amber-300"><ShieldAlert className="h-4 w-4" />Supuestos que deben validarse con el equipo</p>
          <ul className="list-disc space-y-1 pl-5">{result.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
          <p className="mt-2 flex items-center gap-1"><Clock3 className="h-3 w-3" />Fuente: {result.data_source}. Método: {result.solver}.</p>
        </div>
      </section>}
    </main>
  );
}
