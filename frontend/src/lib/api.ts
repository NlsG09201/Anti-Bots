import { resolveApiBaseUrl, resolveDirectApiBaseUrl } from "@/lib/runtime-urls";

// En Vercel: "" → /api/* mismo origen (rewrite a Render). Ignora localhost en el build.
const API_URL = resolveApiBaseUrl();

export function resolveAuthToken(explicit?: string | null): string | undefined {
  const token = explicit ?? getAccessToken();
  return token ?? undefined;
}

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
  baseUrl?: string,
): Promise<T> {
  const authToken = resolveAuthToken(token);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  const csrf = getCsrfToken();
  const apiBase = baseUrl ?? API_URL;
  if (csrf && options.method && options.method !== "GET" && apiBase === API_URL) {
    headers["X-CSRF-Token"] = csrf;
  }

  const response = await fetch(`${apiBase}${path}`, {
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
      return request<T>(path, options, refreshed, baseUrl);
    }
    await handleAuthFailure();
    throw new ApiError(401, "Sesión expirada. Inicia sesión de nuevo.");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: "Request failed" }));
    const message = parseApiErrorMessage(error, response.status);
    throw new ApiError(response.status, message);
  }

  return response.json();
}

const ACCESS_TOKEN_KEY = "ss_access_token";

let memoryAccessToken: string | null = null;

export function setAccessToken(token: string | null) {
  memoryAccessToken = token;
  if (typeof window === "undefined") return;
  if (token) {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  } else {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

export function getAccessToken(): string | null {
  if (memoryAccessToken) return memoryAccessToken;
  if (typeof window === "undefined") return null;
  const stored = sessionStorage.getItem(ACCESS_TOKEN_KEY);
  if (stored) memoryAccessToken = stored;
  return stored;
}

async function handleAuthFailure(): Promise<void> {
  setAccessToken(null);
  const { useAuthStore } = await import("@/stores/authStore");
  useAuthStore.getState().logout();
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  if (!path.startsWith("/login") && !path.startsWith("/register")) {
    window.location.replace("/login?session=expired");
  }
}

let refreshInFlight: Promise<string | null> | null = null;

/** Silently renew access token using HttpOnly refresh cookie (single-flight). */
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      if (!getCsrfToken()) {
        await fetchCsrfToken();
      }
      const csrf = getCsrfToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (csrf) headers["X-CSRF-Token"] = csrf;

      const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers,
      });
      if (!response.ok) return null;
      const data = (await response.json()) as { access_token: string };
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function tryRefreshToken(): Promise<string | null> {
  return refreshAccessToken();
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
    stats: (token: string, streamId?: string) =>
      request<DashboardStats>(
        `/api/v1/streams/dashboard/stats${streamId ? `?stream_id=${streamId}` : ""}`,
        {},
        token,
      ),
    charts: (token: string, streamId?: string) =>
      request<DashboardCharts>(
        `/api/v1/streams/dashboard/charts${streamId ? `?stream_id=${streamId}` : ""}`,
        {},
        token,
      ),
  },
  attacks: {
    list: (token: string, status?: string, streamId?: string) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (streamId) params.set("stream_id", streamId);
      const q = params.toString();
      return request<Attack[]>(`/api/v1/attacks${q ? `?${q}` : ""}`, {}, token);
    },
    mitigate: (
      token: string,
      attackId: string,
      data: { targets?: { type: string; value: string }[]; full_mitigation?: boolean },
    ) =>
      request<{
        action: string;
        bans_created: number;
        targets: number;
        full_mitigation?: boolean;
      }>(`/api/v1/attacks/${attackId}/mitigate`, {
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
    list: (token: string, sync = false) =>
      request<Stream[]>(`/api/v1/streams${sync ? "?sync=true" : ""}`, {}, token),
    watch: (token: string, login: string) =>
      request<Stream>("/api/v1/streams/watch", {
        method: "POST",
        body: JSON.stringify({ login, platform: "twitch" }),
      }, token),
    unwatch: (token: string, streamId: string) =>
      request<{ status: string }>(`/api/v1/streams/watch/${streamId}`, { method: "DELETE" }, token),
    sync: (token: string, streamId: string) =>
      request<Stream>(`/api/v1/streams/${streamId}/sync`, { method: "POST" }, token),
    ingestEvent: (token: string, streamId: string, body: object) =>
      request<{ event_id: string; risk_score: number; attack_created: boolean }>(
        `/api/v1/streams/${streamId}/events`,
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
    viewers: (token: string, streamId: string, filter: "all" | "talking" | "suspected" = "all") =>
      request<Viewer[]>(`/api/v1/streams/${streamId}/viewers?filter=${filter}`, {}, token),
    screenViewers: (token: string, streamId: string) =>
      request<{
        status: string;
        screened: number;
        flagged: number;
        twitch_insights_matched?: number;
        twitch_insights_db_size?: number;
      }>(
        `/api/v1/streams/${streamId}/viewers/screen`,
        { method: "POST" },
        token,
      ),
    loadFullViewers: (token: string, streamId: string) =>
      request<{
        status: string;
        message?: string;
        viewer_count?: number;
        chatters_synced?: number;
        talking_count?: number;
        suspected_count?: number;
        silent_viewers_estimate?: number;
        chat_coverage_percent?: number;
        has_broadcaster_oauth?: boolean;
        source?: string;
        helix_chatters?: number;
      }>(
        `/api/v1/streams/${streamId}/viewers/load-full`,
        { method: "POST" },
        token,
        resolveDirectApiBaseUrl(),
      ),
    syncQuick: (token: string, streamId: string) =>
      request<{
        status: string;
        chatters_synced?: number;
        suspected_count?: number;
        talking_count?: number;
        sync_mode?: string;
        note?: string;
        message?: string;
      }>(`/api/v1/streams/${streamId}/sync/quick`, { method: "POST" }, token),
    monitor: (token: string, streamId: string) =>
      request<{
        status: string;
        chatters_synced?: number;
        suspected_count?: number;
        attack_created?: boolean;
        message?: string;
      }>(`/api/v1/streams/${streamId}/monitor`, { method: "POST" }, token),
    monitorStatus: (token: string, streamId: string) =>
      request<{
        is_live: boolean;
        viewer_count: number;
        active_viewers_tracked: number;
        talking_count: number;
        suspected_bots: number;
        proxy_ips_detected: number;
        silent_viewbots_estimate: number;
        active_attacks: number;
        last_monitor?: string;
        last_quick_sync?: string;
        has_broadcaster_oauth: boolean;
        monitor_mode: boolean;
        note: string;
      }>(`/api/v1/streams/${streamId}/monitor/status`, {}, token),
    channelInvite: (token: string, streamId: string) =>
      request<{
        invite_url: string;
        invite_token: string;
        channel_login: string;
        oauth_start_url: string;
      }>(`/api/v1/streams/${streamId}/channel-invite`, { method: "POST" }, token),
    widgetEmbed: (token: string, streamId: string) =>
      request<{
        stream: Stream;
        ingest_key: string;
        script_url: string;
        api_url: string;
        embed_html: string;
        obs_browser_source_html: string;
        instructions: string[];
      }>(`/api/v1/streams/${streamId}/widget/embed`, {}, token),
    widgetRegenerateKey: (token: string, streamId: string) =>
      request<{ ingest_key: string; status: string }>(
        `/api/v1/streams/${streamId}/widget/key`,
        { method: "POST" },
        token,
      ),
    blockViewer: (
      token: string,
      streamId: string,
      viewerId: string,
      body: { reason?: string; duration_hours?: number; apply_twitch_ban?: boolean },
    ) =>
      request<{ blocked: boolean; message: string; local_only?: boolean; username?: string }>(
        `/api/v1/streams/${streamId}/viewers/${viewerId}/block`,
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
    banSuspected: (
      token: string,
      streamId: string,
      params?: { apply_twitch_ban?: boolean; duration_hours?: number },
    ) => {
      const q = new URLSearchParams();
      if (params?.apply_twitch_ban !== undefined) {
        q.set("apply_twitch_ban", String(params.apply_twitch_ban));
      }
      if (params?.duration_hours !== undefined) {
        q.set("duration_hours", String(params.duration_hours));
      }
      const qs = q.toString();
      return request<{
        status: string;
        targets: number;
        bans_created: number;
        twitch_bans_applied: number;
        attack_id: string;
      }>(
        `/api/v1/streams/${streamId}/viewers/ban-suspected${qs ? `?${qs}` : ""}`,
        { method: "POST" },
        token,
      );
    },
  },
  ai: {
    attackInsight: (token: string, attackId: string) =>
      request<AIInsight>(`/api/v1/ai/attacks/${attackId}/insight`, {}, token),
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

export interface DashboardStats {
  active_attacks: number;
  total_alerts: number;
  blocked_ips: number;
  suspected_bots: number;
  live_viewers: number;
  risk_score_avg: number;
  attacks_last_24h: number;
  mitigations_applied: number;
}

export interface DashboardCharts {
  timeline: { time: string; attacks: number; mitigated: number }[];
  heatmap: { hour: string; risk: number; events: number }[];
  updated_at: string;
}

export interface AIInsight {
  summary: string;
  severity_assessment: string;
  recommended_action: string;
  recommendation: string;
  confidence: number;
  source: string;
}

export interface Stream {
  id: string;
  platform: string;
  external_id?: string;
  channel_name: string;
  is_live: boolean;
  viewer_count: number;
  monitor_mode?: boolean;
  is_owned?: boolean;
  login?: string;
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
  platform_user_id?: string;
  platform_username: string;
  ip_address: string;
  fingerprint_hash?: string;
  risk_score: number;
  is_suspected_bot: boolean;
  is_active: boolean;
  chat_messages?: number;
  behavior_metrics?: Record<string, unknown>;
}
