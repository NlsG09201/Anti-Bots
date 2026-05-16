"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Rocket, ExternalLink } from "lucide-react";
import clsx from "clsx";

interface CheckItem {
  id: string;
  phase: string;
  label: string;
  detail: string;
  link?: string;
}

const CHECKLIST: CheckItem[] = [
  { id: "domain", phase: "Infraestructura", label: "Dominio registrado", detail: "Cloudflare como DNS" },
  { id: "cloudflare", phase: "Infraestructura", label: "Cloudflare SSL Full (strict) + HTTPS forzado", detail: "WAF y Bot Fight activos" },
  { id: "neon", phase: "Base de datos", label: "PostgreSQL en Neon creado", detail: "DATABASE_URL con sslmode=require", link: "https://neon.tech" },
  { id: "upstash", phase: "Cache", label: "Redis en Upstash", detail: "REDIS_URL y CELERY_BROKER_URL", link: "https://upstash.com" },
  { id: "secrets", phase: "Seguridad", label: "Secretos generados (APP/JWT/AES)", detail: "Nunca valores por defecto" },
  { id: "render", phase: "Backend", label: "API desplegada en Render/Fly", detail: "APP_ENV=production, health check /health", link: "https://render.com" },
  { id: "vercel", phase: "Frontend", label: "Frontend en Vercel", detail: "NEXT_PUBLIC_API_URL y WS_URL", link: "https://vercel.com" },
  { id: "cors", phase: "Seguridad", label: "CORS y TRUSTED_HOSTS configurados", detail: "Solo tu dominio real" },
  { id: "cookies", phase: "Seguridad", label: "COOKIE_SECURE=true", detail: "COOKIE_SAMESITE=strict" },
  { id: "twitch-dev", phase: "Twitch", label: "App en dev.twitch.tv", detail: "Client ID + Secret", link: "https://dev.twitch.tv/console" },
  { id: "twitch-redirect", phase: "Twitch", label: "OAuth Redirect URI", detail: "https://api.tudominio.com/api/v1/integrations/twitch/callback" },
  { id: "twitch-webhook", phase: "Twitch", label: "EventSub callback HTTPS:443", detail: "TWITCH_WEBHOOK_SECRET aleatorio" },
  { id: "twitch-connect", phase: "Twitch", label: "Canal conectado en Settings", detail: "Dashboard → Settings → Conectar Twitch" },
  { id: "abuseipdb", phase: "Threat Intel", label: "AbuseIPDB API key", detail: "1000 req/día gratis", link: "https://www.abuseipdb.com/account/api" },
  { id: "ipqs", phase: "Threat Intel", label: "IPQualityScore API key", detail: "VPN/proxy/TOR detection", link: "https://www.ipqualityscore.com" },
  { id: "discord", phase: "Alertas", label: "Discord webhook configurado", detail: "DISCORD_WEBHOOK_URL" },
  { id: "mfa", phase: "Seguridad", label: "MFA activado (admin)", detail: "Settings → Configurar MFA" },
  { id: "docs-hidden", phase: "Verificación", label: "/docs retorna 404", detail: "Swagger oculto en producción" },
  { id: "health", phase: "Verificación", label: "/health responde OK", detail: "curl https://api.tudominio.com/health" },
];

const STORAGE_KEY = "streamshield-deploy-checklist";

export default function DeployPage() {
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) setChecked(JSON.parse(saved));
  }, []);

  const toggle = (id: string) => {
    const next = { ...checked, [id]: !checked[id] };
    setChecked(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const done = Object.values(checked).filter(Boolean).length;
  const total = CHECKLIST.length;
  const progress = Math.round((done / total) * 100);

  const phases = Array.from(new Set(CHECKLIST.map((c) => c.phase)));

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Rocket className="text-cyber-accent" />
            Checklist de despliegue
          </h1>
          <p className="text-cyber-muted text-sm mt-1">
            Progreso guardado en tu navegador — {done}/{total} ({progress}%)
          </p>
        </div>
        <button
          onClick={() => {
            setChecked({});
            localStorage.removeItem(STORAGE_KEY);
          }}
          className="text-xs text-cyber-muted hover:text-cyber-danger"
        >
          Reiniciar
        </button>
      </div>

      <div className="h-2 bg-cyber-bg rounded-full overflow-hidden">
        <div
          className="h-full bg-cyber-accent transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      {phases.map((phase) => (
        <section key={phase} className="cyber-card space-y-2">
          <h2 className="text-sm font-semibold text-cyber-accent uppercase tracking-wider">{phase}</h2>
          {CHECKLIST.filter((c) => c.phase === phase).map((item) => (
            <button
              key={item.id}
              onClick={() => toggle(item.id)}
              className={clsx(
                "w-full flex items-start gap-3 p-3 rounded-lg text-left transition-colors",
                checked[item.id] ? "bg-cyber-accent/10 border border-cyber-accent/20" : "hover:bg-cyber-bg",
              )}
            >
              {checked[item.id] ? (
                <CheckCircle2 className="text-cyber-accent shrink-0 mt-0.5" size={20} />
              ) : (
                <Circle className="text-cyber-muted shrink-0 mt-0.5" size={20} />
              )}
              <div className="flex-1 min-w-0">
                <p className={clsx("text-sm font-medium", checked[item.id] ? "text-cyber-accent" : "text-white")}>
                  {item.label}
                </p>
                <p className="text-xs text-cyber-muted mt-0.5">{item.detail}</p>
              </div>
              {item.link && (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-cyber-muted hover:text-cyber-info shrink-0"
                >
                  <ExternalLink size={14} />
                </a>
              )}
            </button>
          ))}
        </section>
      ))}

      <div className="cyber-card border-cyber-info/20 bg-cyber-info/5">
        <p className="text-sm text-white font-medium mb-2">Guía completa en el repositorio</p>
        <p className="text-xs text-cyber-muted mb-3">
          <strong className="text-cyber-accent">docs/DESPLIEGUE_PASO_A_PASO.md</strong> — incluye despliegue
          sin dominio (URLs gratis de Vercel + Render) y con dominio propio.
        </p>
        <ul className="text-xs text-cyber-muted space-y-1 list-disc list-inside">
          <li>Sin dominio: tu-app.vercel.app + tu-api.onrender.com ($0)</li>
          <li>Con dominio: app.tudominio.com + Cloudflare (~$10/año)</li>
        </ul>
      </div>
    </div>
  );
}
