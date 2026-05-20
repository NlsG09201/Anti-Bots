"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  Globe,
  Loader2,
  MapPin,
  Network,
  RefreshCw,
  Shield,
} from "lucide-react";
import type { ThreatIntelReport } from "@/lib/api";

function BoolBadge({ active, label }: { active: boolean; label: string }) {
  if (!active) return null;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-cyber-danger/15 text-cyber-danger border border-cyber-danger/30">
      {label}
    </span>
  );
}

function riskTone(score: number): string {
  if (score >= 75) return "text-cyber-danger";
  if (score >= 50) return "text-orange-400";
  if (score >= 25) return "text-yellow-400";
  return "text-cyber-accent";
}

interface ThreatIntelPanelProps {
  report: ThreatIntelReport | null;
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  compact?: boolean;
}

export function ThreatIntelPanel({
  report,
  loading,
  error,
  onRefresh,
  compact = false,
}: ThreatIntelPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-cyber-muted">
        <Loader2 className="animate-spin" size={20} />
        Analizando threat intelligence…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-cyber-danger py-4">{error}</p>;
  }

  if (!report) {
    return (
      <p className="text-sm text-cyber-muted py-4">
        Selecciona una IP o busca una dirección para ver el análisis completo.
      </p>
    );
  }

  const geo = report.geo;
  const asn = report.asn;

  return (
    <div className={clsx("space-y-4", compact ? "text-sm" : "")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-lg text-white">{report.ip_address}</p>
          <p className="text-xs text-cyber-muted mt-0.5">
            {report.cached ? "Resultado en caché" : "Análisis en vivo"}
            {report.analyzed_at ? ` · ${new Date(report.analyzed_at).toLocaleString()}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-xs text-cyber-muted">Risk score</p>
            <p className={clsx("text-2xl font-bold font-mono", riskTone(report.risk_score))}>
              {report.risk_score.toFixed(0)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-cyber-muted">Reputación</p>
            <p className="text-xl font-mono text-white">{report.reputation_score.toFixed(0)}</p>
          </div>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="cyber-btn p-2 border border-cyber-border text-cyber-muted hover:text-white cursor-pointer"
              title="Re-analizar"
            >
              <RefreshCw size={18} />
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <BoolBadge active={report.is_vpn} label="VPN" />
        <BoolBadge active={report.is_proxy} label="Proxy" />
        <BoolBadge active={report.is_tor} label="TOR" />
        <BoolBadge active={report.is_datacenter} label="Datacenter" />
        <BoolBadge active={report.is_residential_proxy} label="Residential proxy" />
        <BoolBadge active={report.is_botnet} label="Botnet" />
        <BoolBadge active={report.is_malicious} label="Malicious" />
        {report.recommended_action !== "none" && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-cyber-info/10 text-cyber-info border border-cyber-info/30">
            <Shield size={12} />
            {report.recommended_action}
          </span>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-lg border border-cyber-border/60 bg-cyber-bg/40 p-3 space-y-2">
          <p className="text-xs font-semibold text-cyber-muted uppercase tracking-wide flex items-center gap-1">
            <MapPin size={14} />
            Geolocalización
          </p>
          <p className="text-white">
            {[geo.city, geo.region, geo.country_name || geo.country_code]
              .filter(Boolean)
              .join(", ") || "—"}
          </p>
          {geo.timezone && <p className="text-xs text-cyber-muted">TZ: {geo.timezone}</p>}
          {geo.latitude != null && geo.longitude != null && (
            <p className="text-xs font-mono text-cyber-muted">
              {geo.latitude.toFixed(4)}, {geo.longitude.toFixed(4)}
            </p>
          )}
        </div>

        <div className="rounded-lg border border-cyber-border/60 bg-cyber-bg/40 p-3 space-y-2">
          <p className="text-xs font-semibold text-cyber-muted uppercase tracking-wide flex items-center gap-1">
            <Network size={14} />
            ASN
          </p>
          <p className="text-white font-mono">{asn.number != null ? `AS${asn.number}` : "—"}</p>
          <p className="text-sm text-cyber-muted">{asn.organization || "—"}</p>
          {(asn.is_datacenter || asn.is_hosting) && (
            <p className="text-xs text-orange-400">
              {asn.is_datacenter && "Datacenter "}
              {asn.is_hosting && "Hosting"}
            </p>
          )}
          {asn.risk_keywords?.length > 0 && (
            <p className="text-xs text-cyber-muted">Keywords: {asn.risk_keywords.join(", ")}</p>
          )}
        </div>
      </div>

      <div className="grid sm:grid-cols-3 gap-3 text-center">
        <div className="rounded-lg border border-cyber-border/50 p-2">
          <p className="text-xs text-cyber-muted">Confianza</p>
          <p className="font-mono text-white">{report.confidence.toFixed(0)}%</p>
        </div>
        <div className="rounded-lg border border-cyber-border/50 p-2">
          <p className="text-xs text-cyber-muted">Reportes abuso</p>
          <p className="font-mono text-white">{report.abuse_reports}</p>
        </div>
        <div className="rounded-lg border border-cyber-border/50 p-2">
          <p className="text-xs text-cyber-muted flex items-center justify-center gap-1">
            <Globe size={12} />
            Fuentes
          </p>
          <p className="font-mono text-white text-sm truncate" title={report.sources.join(", ")}>
            {report.sources.length ? report.sources.join(", ") : "—"}
          </p>
        </div>
      </div>

      {report.flags.length > 0 && (
        <div>
          <p className="text-xs text-cyber-muted mb-2 flex items-center gap-1">
            <AlertTriangle size={14} />
            Flags
          </p>
          <div className="flex flex-wrap gap-1.5">
            {report.flags.map((f) => (
              <span
                key={f}
                className="px-2 py-0.5 rounded text-xs font-mono bg-cyber-bg border border-cyber-border text-cyber-muted"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {report.threat_categories.length > 0 && (
        <div>
          <p className="text-xs text-cyber-muted mb-2">Categorías</p>
          <div className="flex flex-wrap gap-1.5">
            {report.threat_categories.map((c) => (
              <span
                key={c}
                className="px-2 py-0.5 rounded text-xs bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
