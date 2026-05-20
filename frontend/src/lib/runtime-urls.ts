/** Evita que un NEXT_PUBLIC_* con localhost en Vercel rompa producción. */

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function isLocalUrl(url: string): boolean {
  return /^(https?|wss?):\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(url);
}

function configuredApiHost(configured: string): string | null {
  try {
    return new URL(configured).hostname;
  } catch {
    return null;
  }
}

/** Cross-origin API URL breaks HttpOnly refresh cookies (Vercel UI → Render API). */
function mustUseSameOriginProxy(hostname: string, configured: string): boolean {
  if (isLocalHost(hostname)) return false;
  const apiHost = configuredApiHost(configured);
  if (!apiHost) return false;
  return apiHost !== hostname;
}

export function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

  if (typeof window === "undefined") {
    return configured && !isLocalUrl(configured) ? configured : "http://localhost:8000";
  }

  if (isLocalHost(window.location.hostname)) {
    return configured || "http://localhost:8000";
  }

  if (configured && !isLocalUrl(configured)) {
    if (mustUseSameOriginProxy(window.location.hostname, configured)) {
      return "";
    }
    return configured;
  }

  return "";
}

/**
 * Llamadas largas (IRC ~30s) van directo al backend para evitar timeout del proxy Vercel (~60s).
 * Auth va por Bearer; no depende de cookies cross-origin.
 */
export function resolveDirectApiBaseUrl(): string {
  const direct =
    process.env.NEXT_PUBLIC_API_DIRECT_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
    "";

  if (typeof window === "undefined") {
    return direct && !isLocalUrl(direct) ? direct : "http://localhost:8000";
  }

  if (isLocalHost(window.location.hostname)) {
    return direct || "http://localhost:8000";
  }

  if (direct && !isLocalUrl(direct)) {
    return direct;
  }

  const proxied = resolveApiBaseUrl();
  if (proxied && !isLocalUrl(proxied)) {
    return proxied;
  }

  // Mismo origen (proxy Vercel → Render): no usar vercel.app para llamadas largas
  if (
    window.location.hostname.endsWith(".vercel.app") ||
    window.location.hostname === "anti-bots.vercel.app"
  ) {
    return "https://anti-bots.onrender.com";
  }

  return window.location.origin;
}

export function resolveWsBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ?? "";

  if (typeof window === "undefined") {
    return configured && !isLocalUrl(configured) ? configured : "ws://localhost:8000";
  }

  if (isLocalHost(window.location.hostname)) {
    return configured || "ws://localhost:8000";
  }

  if (configured && !isLocalUrl(configured)) {
    return configured;
  }

  return "";
}
