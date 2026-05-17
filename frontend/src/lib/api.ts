import { resolveApiBaseUrl } from "@/lib/runtime-urls";

// En Vercel: "" → /api/* mismo origen (rewrite a Render). Ignora localhost en el build.
const API_URL = resolveApiBaseUrl();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function parseApiErrorMessage(error: unknown, status: number): string {
  if (!error || typeof error !== "object") {
    return `HTTP ${status}`;
  }
  const body = error as Record<string, unknown>;
  if (typeof body.message === "string" && body.message) {
    return body.message;
  }
  if (Array.isArray(body.detail)) {
    const parts = body.detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return null;
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (typeof body.detail === "string") {
    return body.detail;
  }
  return `HTTP ${status}`;
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)ss_csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const csrf = getCsrfToken();
  if (csrf && options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = csrf;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  const isAuthAttempt =
    path === "/api/v1/auth/login" ||
    path === "/api/v1/auth/register" ||
    path === "/api/v1/auth/mfa/verify";

  if (response.status === 401 && !isAuthAttempt && path !== "/api/v1/auth/refresh") {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return request<T>(path, options, refreshed);
    }
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: "Request failed" }));
    const message = parseApiErrorMessage(error, response.status);
    throw new ApiError(response.status, message);
  }

  return response.json();
}

let memoryAccessToken: string | null = null;

export function setAccessToken(token: string | null) {
  memoryAccessToken = token;
}

export function getAccessToken(): string | null {
  return memoryAccessToken;
}

async function tryRefreshToken(): Promise<string | null> {
  try {
    const csrf = getCsrfToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (csrf) headers["X-CSRF-Token"] = csrf;

    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers,
    });
    if (!response.ok) return null;
    const data = await response.json();
    memoryAccessToken = data.access_token;
    return data.access_token;
  } catch {
    return null;
  }
}

export async function fetchCsrfToken(): Promise<void> {
  await fetch(`${API_URL}/api/v1/auth/csrf`, { credentials: "include" });
}

export const api = {
  auth: {
    login: async (email: string, password: string) => {
      await fetchCsrfToken();
      const data = await request<{
        access_token: string;
        expires_in: number;
        mfa_required?: boolean;
        mfa_token?: string;
      }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      if (!data.mfa_required) setAccessToken(data.access_token);
      return data;
    },
    verifyMfa: async (mfaToken: string, code: string) => {
      const data = await request<{ access_token: string }>(
        "/api/v1/auth/mfa/verify",
        { method: "POST", body: JSON.stringify({ mfa_token: mfaToken, code }) },
      );
      setAccessToken(data.access_token);
      return data;
    },
    register: async (body: {
      email: string;
      username: string;
      password: string;
      tenant_name: string;
    }) => {
      await fetchCsrfToken();
      const data = await request<{ access_token: string }>(
        "/api/v1/auth/register",
        { method: "POST", body: JSON.stringify(body) },
      );
      setAccessToken(data.access_token);
      return data;
    },
    logout: async (token: string) => {
      await request("/api/v1/auth/logout", { method: "POST" }, token);
      setAccessToken(null);
    },
    me: (token: string) =>
      request<{ id: string; email: string; username: string; role: string }>(
        "/api/v1/auth/me",
        {},
        token,
      ),
  },
  dashboard: {
    stats: (token: string) =>
      request<{
        active_attacks: number;
        total_alerts: number;
        blocked_ips: number;
        suspected_bots: number;
        live_viewers: number;
        risk_score_avg: number;
        attacks_last_24h: number;
        mitigations_applied: number;
      }>("/api/v1/streams/dashboard/stats", {}, token),
  },
  attacks: {
    list: (token: string, status?: string) =>
      request<Attack[]>(`/api/v1/attacks${status ? `?status=${status}` : ""}`, {}, token),
    mitigate: (token: string, attackId: string, data: object) =>
      request(`/api/v1/attacks/${attackId}/mitigate`, {
        method: "POST",
        body: JSON.stringify(data),
      }, token),
  },
  alerts: {
    list: (token: string) => request<Alert[]>("/api/v1/alerts", {}, token),
    acknowledge: (token: string, alertId: string) =>
      request(`/api/v1/alerts/${alertId}/acknowledge`, { method: "PATCH" }, token),
  },
  bans: {
    list: (token: string) => request<Ban[]>("/api/v1/bans", {}, token),
  },
  fingerprints: {
    list: (token: string) => request<Fingerprint[]>("/api/v1/fingerprints", {}, token),
  },
  ips: {
    list: (token: string) => request<SuspiciousIP[]>("/api/v1/ips", {}, token),
  },
  streams: {
    list: (token: string) => request<Stream[]>("/api/v1/streams", {}, token),
    viewers: (token: string, streamId: string) =>
      request<Viewer[]>(`/api/v1/streams/${streamId}/viewers`, {}, token),
  },
  mfa: {
    status: (token: string) =>
      request<{ enabled: boolean; required_for_role: boolean }>("/api/v1/auth/mfa/status", {}, token),
    setup: (token: string) =>
      request<{ secret: string; provisioning_uri: string; qr_code_base64: string }>(
        "/api/v1/auth/mfa/setup",
        { method: "POST" },
        token,
      ),
    enable: (token: string, code: string) =>
      request("/api/v1/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) }, token),
    disable: (token: string, code: string) =>
      request("/api/v1/auth/mfa/disable", { method: "POST", body: JSON.stringify({ code }) }, token),
  },
  users: {
    list: (token: string) => request<TenantUser[]>("/api/v1/users", {}, token),
    updateRole: (token: string, userId: string, role: string) =>
      request<TenantUser>(`/api/v1/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }, token),
    updateStatus: (token: string, userId: string, isActive: boolean) =>
      request<TenantUser>(`/api/v1/users/${userId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      }, token),
  },
  twitch: {
    status: (token: string) =>
      request<{
        connected: boolean;
        configured: boolean;
        credentials_ok: boolean;
        redirect_uri: string;
        channels: { id: string; channel_name: string; external_id: string; is_live: boolean }[];
      }>("/api/v1/integrations/twitch/status", {}, token),
    setup: (token: string) =>
      request<{
        redirect_uri: string;
        client_id_prefix: string;
        credentials_ok: boolean;
        client_id_equals_secret: boolean;
        register_at: string;
        hint: string;
      }>("/api/v1/integrations/twitch/setup", {}, token),
    authorize: (token: string) =>
      request<{ authorization_url: string }>("/api/v1/integrations/twitch/authorize", {}, token),
  },
};

export interface Attack {
  id: string;
  attack_type: string;
  severity: string;
  status: string;
  risk_score: number;
  confidence: number;
  correlation_id: string;
  source_ips: string[];
  fingerprints: string[];
  mitigation_action: string;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface Alert {
  id: string;
  title: string;
  message: string;
  severity: string;
  status: string;
  created_at: string;
}

export interface Ban {
  id: string;
  target_type: string;
  target_value: string;
  ban_type: string;
  reason: string;
  is_active: boolean;
  is_automated: boolean;
  created_at: string;
}

export interface Fingerprint {
  hash: string;
  risk_score: number;
  is_headless: boolean;
  is_blocked: boolean;
  occurrence_count: number;
  automation_flags: string[];
}

export interface SuspiciousIP {
  ip_address: string;
  reputation_score: number;
  is_proxy: boolean;
  is_vpn: boolean;
  is_tor: boolean;
  is_datacenter: boolean;
  is_blocked: boolean;
  country_code: string;
}

export interface Stream {
  id: string;
  platform: string;
  channel_name: string;
  is_live: boolean;
  viewer_count: number;
}

export interface TenantUser {
  id: string;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  mfa_enabled: boolean;
  last_login: string | null;
}

export interface Viewer {
  id: string;
  platform_username: string;
  ip_address: string;
  risk_score: number;
  is_suspected_bot: boolean;
  is_active: boolean;
}
