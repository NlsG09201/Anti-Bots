/** Evita que un NEXT_PUBLIC_* con localhost en Vercel rompa producción. */

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function isLocalUrl(url: string): boolean {
  return /^(https?|wss?):\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(url);
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
    return configured;
  }

  return "";
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
