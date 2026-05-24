import { resolveApiBaseUrl, resolveDirectApiBaseUrl } from "@/lib/runtime-urls";

// En Vercel: "" → /api/* mismo origen (rewrite a Render). Ignora localhost en el build.
const API_URL = resolveApiBaseUrl();

/** Token explícito o de sessionStorage; null/undefined si no hay sesión. */
export type ApiAuthToken = string | null | undefined;

export function resolveAuthToken(explicit?: ApiAuthToken): string | undefined {
  const trimmed = explicit?.trim();
  const token = (trimmed ? trimmed : getAccessToken()?.trim()) || undefined;
  return token;
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
  if (body.detail && typeof body.detail === "object") {
    const nested = body.detail as Record<string, unknown>;
    if (typeof nested.message === "string" && nested.message) {
      return nested.message;
    }
    if (typeof nested.error === "string" && nested.error) {
      return nested.error;
    }
  }
  return `HTTP ${status}`;
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)ss_csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** POST/PUT/PATCH al mismo origen (proxy Vercel o API relativa) requieren CSRF si hay cookie de sesión. */
function shouldAttachCsrf(baseUrl?: string): boolean {
  if (typeof window === "undefined") return false;
  const raw = (baseUrl ?? API_URL).trim();
  if (!raw) return true;
  try {
    const target = new URL(raw, window.location.origin);
    return target.origin === window.location.origin;
  } catch {
    return false;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: ApiAuthToken,
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
  if (
    csrf &&
    options.method &&
    options.method !== "GET" &&
    shouldAttachCsrf(apiBase)
  ) {
    headers["X-CSRF-Token"] = csrf;
  }

  if (sessionTerminated && path !== "/api/v1/auth/login" && path !== "/api/v1/auth/register") {
    throw new ApiError(401, "Sesión expirada. Inicia sesión de nuevo.");
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

  if (response.status === 429) {
    throw new ApiError(429, "Demasiadas peticiones. Espera unos segundos e inténtalo de nuevo.");
  }

  if (response.status === 502 || response.status === 504) {
    throw new ApiError(
      response.status,
      "El servidor tardó demasiado (timeout del proxy). La petición larga debe ir directo al API; recarga la página e inténtalo de nuevo.",
    );
  }

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

let authFailureInFlight = false;
let sessionTerminated = false;

/** Call after successful login so API requests resume. */
export function resetAuthSessionState(): void {
  sessionTerminated = false;
  authFailureInFlight = false;
}

async function syncAuthTokenToStore(token: string): Promise<void> {
  setAccessToken(token);
  const { useAuthStore } = await import("@/stores/authStore");
  useAuthStore.getState().setTokens(token);
}

async function handleAuthFailure(): Promise<void> {
  if (sessionTerminated || authFailureInFlight) return;
  authFailureInFlight = true;
  sessionTerminated = true;

  setAccessToken(null);
  const { useAuthStore } = await import("@/stores/authStore");
  useAuthStore.getState().logout();

  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("streamshield:session-expired"));
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
      const attempt = async () => {
        const csrf = getCsrfToken();
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (csrf) headers["X-CSRF-Token"] = csrf;

        return fetch(`${API_URL}/api/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers,
        });
      };

      let response = await attempt();
      if (response.status === 403) {
        await fetchCsrfToken();
        response = await attempt();
      }
      if (!response.ok) return null;
      const data = (await response.json()) as { access_token: string };
      await syncAuthTokenToStore(data.access_token);
      sessionTerminated = false;
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

let bootstrapInFlight: Promise<string | null> | null = null;

/** Validate bearer without triggering login redirect (used during bootstrap). */
async function probeAccessToken(token: string): Promise<"valid" | "invalid" | "rate_limited"> {
  const response = await fetch(`${API_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "include",
  });
  if (response.status === 401) return "invalid";
  if (response.status === 429) return "rate_limited";
  return response.ok ? "valid" : "invalid";
}

/**
 * Restore a valid access token before dashboard queries run (single-flight).
 * Refresh first (HttpOnly cookie); validate existing bearer only if needed.
 */
export async function bootstrapAuthSession(): Promise<string | null> {
  if (bootstrapInFlight) return bootstrapInFlight;

  bootstrapInFlight = (async () => {
    try {
      resetAuthSessionState();

      const refreshed = await refreshAccessToken();
      if (refreshed) return refreshed;

      const existing = getAccessToken();
      if (!existing) return null;

      const status = await probeAccessToken(existing);
      if (status === "valid") {
        await syncAuthTokenToStore(existing);
        return existing;
      }
      if (status === "rate_limited") {
        const retryRefresh = await refreshAccessToken();
        if (retryRefresh) return retryRefresh;
        await syncAuthTokenToStore(existing);
        return existing;
      }

      setAccessToken(null);
      return null;
    } finally {
      bootstrapInFlight = null;
    }
  })();

  return bootstrapInFlight;
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
    logout: async (token: ApiAuthToken) => {
      await request("/api/v1/auth/logout", { method: "POST" }, token);
      setAccessToken(null);
    },
    me: (token: ApiAuthToken) =>
      request<{ id: string; email: string; username: string; role: string }>(
        "/api/v1/auth/me",
        {},
        token,
      ),
  },
  dashboard: {
    stats: (token: ApiAuthToken, streamId?: string) =>
      request<DashboardStats>(
        `/api/v1/streams/dashboard/stats${streamId ? `?stream_id=${streamId}` : ""}`,
        {},
        token,
      ),
    charts: (token: ApiAuthToken, streamId?: string) =>
      request<DashboardCharts>(
        `/api/v1/streams/dashboard/charts${streamId ? `?stream_id=${streamId}` : ""}`,
        {},
        token,
      ),
  },
  viewerFlow: {
    overview: (token: ApiAuthToken) =>
      request<ViewerFlowOverview>("/api/v1/viewer-flow/overview", {}, token),
    stream: (token: ApiAuthToken, streamId: string) =>
      request<ViewerFlowStreamSnapshot & { enabled?: boolean }>(
        `/api/v1/viewer-flow/streams/${streamId}`,
        {},
        token,
      ),
    scan: (token: ApiAuthToken, streamId: string) =>
      request<{ ok: boolean; sync: Record<string, unknown>; flow: unknown }>(
        `/api/v1/viewer-flow/scan/${streamId}`,
        { method: "POST" },
        token,
      ),
    crossPlatform: (token: ApiAuthToken, username: string) =>
      request<{ username: string; cross_platform_hits: number; coordinated_risk: boolean }>(
        `/api/v1/viewer-flow/cross-platform?username=${encodeURIComponent(username)}`,
        {},
        token,
      ),
  },
  platformHealth: {
    overview: (token: ApiAuthToken) =>
      request<PlatformHealthOverview>("/api/v1/platform-health/overview", {}, token),
    streams: (token: ApiAuthToken) =>
      request<{ enabled: boolean; streams: PlatformHealthStream[]; count: number }>(
        "/api/v1/platform-health/streams",
        {},
        token,
      ),
    integrations: (token: ApiAuthToken) =>
      request<{ enabled: boolean; integrations: IntegrationProbe[] }>(
        "/api/v1/platform-health/integrations",
        {},
        token,
      ),
    audit: (token: ApiAuthToken) =>
      request<PlatformHealthOverview>(
        "/api/v1/platform-health/audit",
        { method: "POST" },
        token,
      ),
    monitorsStatus: (token: ApiAuthToken) =>
      request<PlatformMonitorHealthStatus>(
        "/api/v1/platform-health/monitors/status",
        {},
        token,
      ),
  },
  twitchbots: {
    overview: (token: ApiAuthToken) =>
      request<TwitchBotsOverview>("/api/v1/twitchbots/overview", {}, token),
    detections: (token: ApiAuthToken, limit = 40) =>
      request<{ enabled: boolean; detections: TwitchBotsDetection[]; count: number }>(
        `/api/v1/twitchbots/detections?limit=${limit}`,
        {},
        token,
      ),
    verify: (
      token: ApiAuthToken,
      body: { username?: string; platform_user_id?: string; stream_id?: string },
    ) =>
      request<{ result: Record<string, unknown>; verdict: Record<string, unknown> }>(
        "/api/v1/twitchbots/verify",
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
    verifyBatch: (
      token: ApiAuthToken,
      users: { username?: string; platform_user_id?: string }[],
      streamId?: string,
      applySessions = false,
    ) =>
      request<{
        status: string;
        verified?: number;
        known_bots?: number;
        job_id?: string;
        count?: number;
      }>(
        "/api/v1/twitchbots/verify/batch",
        {
          method: "POST",
          body: JSON.stringify({
            users,
            stream_id: streamId,
            apply_sessions: applySessions,
          }),
        },
        token,
      ),
  },
  soc: {
    overview: (token: ApiAuthToken) =>
      request<{ stats: DashboardStats; soc: SocOverview }>(
        "/api/v1/soc/overview",
        {},
        token,
      ),
    feed: (token: ApiAuthToken, limit = 50) =>
      request<{ events: SocLiveFeedEvent[] }>(
        `/api/v1/soc/feed?limit=${limit}`,
        {},
        token,
      ),
    refresh: (token: ApiAuthToken) =>
      request<{ ok: boolean; soc: SocOverview }>(
        "/api/v1/soc/refresh",
        { method: "POST" },
        token,
      ),
    monitorsStatus: (token: ApiAuthToken) =>
      request<{
        enabled: boolean;
        running: boolean;
        active_monitors: string[];
        count: number;
        max_streams: number;
      }>("/api/v1/soc/monitors/status", {}, token),
  },
  liveIntelligence: {
    overview: (token: ApiAuthToken) =>
      request<LiveIntelOverviewResponse>("/api/v1/live-intelligence/overview", {}, token),
    streams: (token: ApiAuthToken) =>
      request<{ streams: LiveIntelStreamRow[]; count: number }>(
        "/api/v1/live-intelligence/streams",
        {},
        token,
      ),
    stream: (token: ApiAuthToken, streamId: string) =>
      request<{ stream_id: string; snapshot: LiveStreamSnapshot | null; history: unknown[] }>(
        `/api/v1/live-intelligence/streams/${streamId}`,
        {},
        token,
      ),
    history: (token: ApiAuthToken, streamId: string, limit = 200) =>
      request<{ stream_id: string; points: LiveIntelHistoryPoint[]; count: number }>(
        `/api/v1/live-intelligence/streams/${streamId}/history?limit=${limit}`,
        {},
        token,
      ),
    compare: (token: ApiAuthToken, streamIds: string[]) =>
      request<{ rows: StreamComparisonRow[]; insights: string[] }>(
        "/api/v1/live-intelligence/compare",
        {
          method: "POST",
          body: JSON.stringify({ stream_ids: streamIds }),
        },
        token,
      ),
    anomalies: (token: ApiAuthToken, limit = 40) =>
      request<{ anomalies: LiveIntelAnomaly[]; count: number }>(
        `/api/v1/live-intelligence/anomalies?limit=${limit}`,
        {},
        token,
      ),
    status: (token: ApiAuthToken) =>
      request<{ enabled: boolean; running: boolean; cached_snapshots: number }>(
        "/api/v1/live-intelligence/status",
        {},
        token,
      ),
  },
  streamingIntelligence: {
    overview: (token: ApiAuthToken) =>
      request<ThreatIntelOverviewResponse>("/api/v1/streaming-intelligence/overview", {}, token),
    stream: (token: ApiAuthToken, streamId: string) =>
      request<ThreatIntelStreamResponse>(
        `/api/v1/streaming-intelligence/streams/${streamId}`,
        {},
        token,
      ),
    engagement: (token: ApiAuthToken, streamId: string) =>
      request<{ stream_id: string; engagement: EngagementMetrics; source: string }>(
        `/api/v1/streaming-intelligence/streams/${streamId}/engagement`,
        {},
        token,
      ),
    graph: (token: ApiAuthToken, streamId: string) =>
      request<{ stream_id: string; graph: ThreatGraphSnapshot }>(
        `/api/v1/streaming-intelligence/streams/${streamId}/graph`,
        {},
        token,
      ),
    topEntities: (token: ApiAuthToken, limit = 50) =>
      request<{ entities: ThreatEntitySummary[]; count: number }>(
        `/api/v1/streaming-intelligence/entities/top?limit=${limit}`,
        {},
        token,
      ),
    crossPlatform: (token: ApiAuthToken, username: string) =>
      request<{ username: string; matches: CrossPlatformMatch[] }>(
        `/api/v1/streaming-intelligence/cross-platform?username=${encodeURIComponent(username)}`,
        {},
        token,
      ),
  },
  attacks: {
    list: (token: ApiAuthToken, status?: string, streamId?: string) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (streamId) params.set("stream_id", streamId);
      const q = params.toString();
      return request<Attack[]>(`/api/v1/attacks${q ? `?${q}` : ""}`, {}, token);
    },
    mitigate: (
      token: ApiAuthToken,
      attackId: string,
      data: { targets?: { type: string; value: string }[]; full_mitigation?: boolean },
    ) =>
      request<{
        action: string;
        bans_created: number;
        targets: number;
        full_mitigation?: boolean;
        acknowledge_only?: boolean;
        message?: string | null;
      }>(`/api/v1/attacks/${attackId}/mitigate`, {
        method: "POST",
        body: JSON.stringify(data),
      }, token),
  },
  alerts: {
    list: (token: ApiAuthToken) => request<Alert[]>("/api/v1/alerts", {}, token),
    acknowledge: (token: ApiAuthToken, alertId: string) =>
      request(`/api/v1/alerts/${alertId}/acknowledge`, { method: "PATCH" }, token),
  },
  bans: {
    list: (token: ApiAuthToken) => request<Ban[]>("/api/v1/bans", {}, token),
  },
  fingerprints: {
    list: (
      token: ApiAuthToken,
      params?: {
        stream_id?: string;
        q?: string;
        min_risk?: number;
        limit?: number;
      },
    ) => {
      const search = new URLSearchParams();
      if (params?.stream_id) search.set("stream_id", params.stream_id);
      if (params?.q) search.set("q", params.q);
      if (params?.min_risk != null) search.set("min_risk", String(params.min_risk));
      if (params?.limit != null) search.set("limit", String(params.limit));
      const qs = search.toString();
      return request<{ fingerprints: Fingerprint[]; count: number }>(
        `/api/v1/fingerprints${qs ? `?${qs}` : ""}`,
        {},
        token,
      );
    },
    analyzeAdvanced: (token: ApiAuthToken, body: object) =>
      request<AdvancedFingerprintResult>(
        "/api/v1/detection/fingerprint/advanced",
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
  },
  ips: {
    list: (token: ApiAuthToken) => request<SuspiciousIP[]>("/api/v1/ips", {}, token),
    analyze: (token: ApiAuthToken, ip: string, forceRefresh = false) => {
      if (forceRefresh) {
        return request<ThreatIntelReport>(
          `/api/v1/threat-intel/analyze?ip_address=${encodeURIComponent(ip)}&force_refresh=true`,
          {},
          token,
        );
      }
      return request<ThreatIntelReport>(
        `/api/v1/detection/analyze-ip?ip_address=${encodeURIComponent(ip)}`,
        { method: "POST" },
        token,
      );
    },
  },
  streams: {
    list: (token: ApiAuthToken, sync = false) =>
      request<Stream[]>(`/api/v1/streams${sync ? "?sync=true" : ""}`, {}, token),
    watch: (
      token: ApiAuthToken,
      login: string,
      platform: "twitch" | "kick" | "youtube" | "tiktok" = "twitch",
    ) =>
      request<Stream>("/api/v1/streams/watch", {
        method: "POST",
        body: JSON.stringify({ login, platform }),
      }, token),
    unwatch: (token: ApiAuthToken, streamId: string) =>
      request<{ status: string }>(`/api/v1/streams/watch/${streamId}`, { method: "DELETE" }, token),
    sync: (token: ApiAuthToken, streamId: string) =>
      request<Stream>(`/api/v1/streams/${streamId}/sync`, { method: "POST" }, token),
    ingestEvent: (token: ApiAuthToken, streamId: string, body: object) =>
      request<{ event_id: string; risk_score: number; attack_created: boolean }>(
        `/api/v1/streams/${streamId}/events`,
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
    viewers: (token: ApiAuthToken, streamId: string, filter: "all" | "talking" | "suspected" = "all") =>
      request<Viewer[]>(`/api/v1/streams/${streamId}/viewers?filter=${filter}`, {}, token),
    screenViewers: (token: ApiAuthToken, streamId: string) =>
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
    loadFullViewers: (token: ApiAuthToken, streamId: string) =>
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
    syncQuick: (token: ApiAuthToken, streamId: string) =>
      request<{
        status: string;
        viewer_count?: number;
        chatters_synced?: number;
        suspected_count?: number;
        talking_count?: number;
        sync_mode?: string;
        note?: string;
        message?: string;
      }>(
        `/api/v1/streams/${streamId}/sync/quick`,
        { method: "POST" },
        token,
        resolveDirectApiBaseUrl(),
      ),
    monitor: (token: ApiAuthToken, streamId: string) =>
      request<{
        status: string;
        chatters_synced?: number;
        suspected_count?: number;
        attack_created?: boolean;
        message?: string;
      }>(
        `/api/v1/streams/${streamId}/monitor`,
        { method: "POST" },
        token,
        resolveDirectApiBaseUrl(),
      ),
    monitorStatus: (token: ApiAuthToken, streamId: string) =>
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
    channelInvite: (token: ApiAuthToken, streamId: string) =>
      request<{
        invite_url: string;
        invite_token: string;
        channel_login: string;
        oauth_start_url: string;
      }>(`/api/v1/streams/${streamId}/channel-invite`, { method: "POST" }, token),
    widgetEmbed: (token: ApiAuthToken, streamId: string) =>
      request<{
        stream: Stream;
        ingest_key: string;
        script_url: string;
        api_url: string;
        embed_html: string;
        obs_browser_source_html: string;
        instructions: string[];
      }>(`/api/v1/streams/${streamId}/widget/embed`, {}, token),
    widgetRegenerateKey: (token: ApiAuthToken, streamId: string) =>
      request<{ ingest_key: string; status: string }>(
        `/api/v1/streams/${streamId}/widget/key`,
        { method: "POST" },
        token,
      ),
    blockViewer: (
      token: ApiAuthToken,
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
      token: ApiAuthToken,
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
    attackInsight: (token: ApiAuthToken, attackId: string) =>
      request<AIInsight>(`/api/v1/ai/attacks/${attackId}/insight`, {}, token),
  },
  mfa: {
    status: (token: ApiAuthToken) =>
      request<{ enabled: boolean; required_for_role: boolean }>("/api/v1/auth/mfa/status", {}, token),
    setup: (token: ApiAuthToken) =>
      request<{ secret: string; provisioning_uri: string; qr_code_base64: string }>(
        "/api/v1/auth/mfa/setup",
        { method: "POST" },
        token,
      ),
    enable: (token: ApiAuthToken, code: string) =>
      request("/api/v1/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) }, token),
    disable: (token: ApiAuthToken, code: string) =>
      request("/api/v1/auth/mfa/disable", { method: "POST", body: JSON.stringify({ code }) }, token),
  },
  users: {
    list: (token: ApiAuthToken) => request<TenantUser[]>("/api/v1/users", {}, token),
    updateRole: (token: ApiAuthToken, userId: string, role: string) =>
      request<TenantUser>(`/api/v1/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }, token),
    updateStatus: (token: ApiAuthToken, userId: string, isActive: boolean) =>
      request<TenantUser>(`/api/v1/users/${userId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      }, token),
  },
  threatIntel: {
    analyze: (token: ApiAuthToken, ip: string, forceRefresh = false) =>
      request<ThreatIntelReport>(
        `/api/v1/threat-intel/analyze?ip_address=${encodeURIComponent(ip)}&force_refresh=${forceRefresh}`,
        {},
        token,
      ),
    analyzeBatch: (token: ApiAuthToken, ips: string[]) =>
      request<{ results: ThreatIntelReport[]; count: number }>(
        "/api/v1/threat-intel/analyze/batch",
        { method: "POST", body: JSON.stringify({ ip_addresses: ips }) },
        token,
      ),
  },
  security: {
    dashboard: (
      token: string,
      opts?: { hours?: number; streamId?: string },
    ) => {
      const params = new URLSearchParams();
      if (opts?.hours) params.set("hours", String(opts.hours));
      if (opts?.streamId) params.set("stream_id", opts.streamId);
      const q = params.toString();
      return request<SecurityDashboard>(
        `/api/v1/security/dashboard${q ? `?${q}` : ""}`,
        {},
        token,
      );
    },
  },
  twitch: {
    status: (token: ApiAuthToken) =>
      request<{
        connected: boolean;
        configured: boolean;
        credentials_ok: boolean;
        redirect_uri: string;
        channels: { id: string; channel_name: string; external_id: string; is_live: boolean }[];
      }>("/api/v1/integrations/twitch/status", {}, token),
    setup: (token: ApiAuthToken) =>
      request<{
        redirect_uri: string;
        client_id_prefix: string;
        credentials_ok: boolean;
        client_id_equals_secret: boolean;
        register_at: string;
        hint: string;
      }>("/api/v1/integrations/twitch/setup", {}, token),
    authorize: (token: ApiAuthToken) =>
      request<{ authorization_url: string }>("/api/v1/integrations/twitch/authorize", {}, token),
  },
  kick: {
    status: (token: ApiAuthToken) =>
      request<{
        connected: boolean;
        configured: boolean;
        redirect_uri: string;
        channels: {
          id: string;
          channel_name: string;
          external_id: string;
          is_live: boolean;
          has_oauth: boolean;
        }[];
      }>("/api/v1/integrations/kick/status", {}, token),
    setup: (token: ApiAuthToken) =>
      request<{
        redirect_uri: string;
        credentials_ok: boolean;
        register_at: string;
        hint: string;
      }>("/api/v1/integrations/kick/setup", {}, token),
    authorize: (token: ApiAuthToken) =>
      request<{ authorization_url: string }>("/api/v1/integrations/kick/authorize", {}, token),
  },
  youtube: {
    status: (token: ApiAuthToken) =>
      request<{
        connected: boolean;
        configured: boolean;
        redirect_uri: string;
        api_key_set: boolean;
        channels: {
          id: string;
          channel_name: string;
          external_id: string;
          is_live: boolean;
          has_oauth: boolean;
        }[];
      }>("/api/v1/integrations/youtube/status", {}, token),
    setup: (token: ApiAuthToken) =>
      request<{
        redirect_uri: string;
        credentials_ok: boolean;
        register_at: string;
        hint: string;
      }>("/api/v1/integrations/youtube/setup", {}, token),
    authorize: (token: ApiAuthToken) =>
      request<{ authorization_url: string }>("/api/v1/integrations/youtube/authorize", {}, token),
  },
  aiIntel: {
    health: (token: ApiAuthToken) =>
      request<{
        status: string;
        models_loaded: string[];
        model_version: string;
        mode: string;
      }>("/api/v1/ai-intel/health", {}, token),
    predictions: (token: ApiAuthToken) =>
      request<{
        predictions: AIPredictionEntry[];
        count: number;
      }>("/api/v1/ai-intel/predictions", {}, token),
    streamPrediction: (token: ApiAuthToken, streamId: string) =>
      request<{ stream_id: string; prediction: AIAssessment | null }>(
        `/api/v1/ai-intel/streams/${streamId}/prediction`,
        {},
        token,
      ),
    feedback: (
      token: ApiAuthToken,
      body: {
        stream_id: string;
        was_true_positive: boolean;
        classification?: string;
        notes?: string;
        features?: Record<string, number>;
      },
    ) =>
      request<{ status: string; total_samples: number }>(
        "/api/v1/ai-intel/feedback",
        { method: "POST", body: JSON.stringify(body) },
        token,
      ),
    train: (token: ApiAuthToken) =>
      request<Record<string, unknown>>(
        "/api/v1/ai-intel/train",
        { method: "POST" },
        token,
      ),
  },
  wekaJ48: {
    health: (token: ApiAuthToken) =>
      request<{
        enabled: boolean;
        model_loaded: boolean;
        backend: string | null;
        weka_runtime: boolean;
        weka_python_available?: boolean;
        weka_python_installed?: boolean;
        weka_python_enabled?: boolean;
        java_available?: boolean;
        jvm_started?: boolean;
        weka_runtime_ready?: boolean;
        last_error?: string | null;
        trained_at?: string | null;
        training_samples?: number | null;
        meta?: Record<string, unknown>;
        model_path?: string;
      }>("/api/v1/ml/weka-j48/health", {}, token),
    startJvm: (token: ApiAuthToken) =>
      request<{
        ok: boolean;
        jvm_started?: boolean;
        error?: string;
        already_running?: boolean;
      }>(
        "/api/v1/ml/weka-j48/jvm/start",
        { method: "POST" },
        token,
        resolveDirectApiBaseUrl(),
      ),
    predictStream: (token: ApiAuthToken, streamId: string, limit = 500) =>
      request<{
        stream_id: string;
        count: number;
        predicted_bots: number;
        predictions: WekaJ48Prediction[];
      }>(
        `/api/v1/ml/weka-j48/predict/stream/${streamId}?limit=${limit}`,
        {},
        token,
      ),
    preview: (
      token: ApiAuthToken,
      source: "registered_bots" | "channel_flow" | "mixed" = "mixed",
      includeTwitchInsights = true,
    ) =>
      request<{
        source: string;
        rows: number;
        bots: number;
        humans: number;
        ready: boolean;
        min_required: number;
        twitch_insights_db_size?: number;
      }>(
        `/api/v1/ml/weka-j48/dataset/preview?source=${source}&include_twitch_insights=${includeTwitchInsights}`,
        {},
        token,
      ),
    train: (
      token: ApiAuthToken,
      opts?: {
        limit?: number;
        source?: "registered_bots" | "channel_flow" | "mixed";
        includeTwitchInsights?: boolean;
      },
    ) => {
      const limit = opts?.limit ?? 5000;
      const source = opts?.source ?? "mixed";
      const ti = opts?.includeTwitchInsights ?? true;
      return request<{
        ok: boolean;
        samples?: number;
        bots?: number;
        humans?: number;
        training?: Record<string, unknown>;
        dataset?: Record<string, unknown>;
        error?: string;
        hint?: string;
      }>(
        `/api/v1/ml/weka-j48/train?limit=${limit}&source=${source}&include_twitch_insights=${ti}`,
        { method: "POST" },
        token,
        resolveDirectApiBaseUrl(),
      );
    },
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

export interface FingerprintChannelRef {
  stream_id: string;
  channel_name: string;
  platform: string;
}

export interface Fingerprint {
  hash: string;
  risk_score: number;
  is_headless: boolean;
  is_blocked: boolean;
  occurrence_count: number;
  automation_flags: string[];
  event_count?: number;
  channels?: FingerprintChannelRef[];
  channel_count?: number;
}

export interface ThreatIntelReport {
  ip_address: string;
  reputation_score: number;
  risk_score: number;
  confidence: number;
  is_vpn: boolean;
  is_proxy: boolean;
  is_tor: boolean;
  is_datacenter: boolean;
  is_residential_proxy: boolean;
  is_botnet: boolean;
  is_malicious: boolean;
  asn: {
    number: number | null;
    organization: string | null;
    is_datacenter: boolean;
    is_hosting: boolean;
    risk_keywords: string[];
  };
  geo: {
    country_code: string | null;
    country_name: string | null;
    city: string | null;
    region: string | null;
    latitude: number | null;
    longitude: number | null;
    timezone: string | null;
  };
  abuse_reports: number;
  threat_categories: string[];
  flags: string[];
  sources: string[];
  recommended_action: string;
  cached: boolean;
  analyzed_at: string | null;
}

export interface AdvancedFingerprintResult {
  device_hash: string;
  fingerprint_hash: string;
  session_key: string;
  trust_score: number;
  risk_score: number;
  confidence_score: number;
  is_automation: boolean;
  is_headless: boolean;
  is_blocked: boolean;
  automation_flags: string[];
  signals: Record<string, unknown>;
  correlated_sessions: string[];
  correlation_strength: number;
  correlation: Record<string, unknown>;
  recommended_action: string;
}

export interface SuspiciousIP {
  ip_address: string;
  reputation_score: number;
  risk_score: number;
  is_proxy: boolean;
  is_vpn: boolean;
  is_tor: boolean;
  is_datacenter: boolean;
  is_residential_proxy: boolean;
  is_botnet: boolean;
  is_blocked: boolean;
  country_code: string | null;
  asn: number | null;
  asn_organization: string | null;
  abuse_reports: number;
  flags: string[];
  sources: string[];
  recommended_action: string;
  analyzed_at: string | null;
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

export interface SocPlatformMetrics {
  live_streams: number;
  viewers: number;
  suspected: number;
  events_1h: number;
  active_attacks: number;
}

export interface SocOverview {
  platforms: Record<string, SocPlatformMetrics>;
  threat_score: number;
  threat_level: "low" | "medium" | "high" | "critical";
  global: {
    live_viewers: number;
    suspected_bots: number;
    active_attacks: number;
  };
  updated_at: string;
}

export interface ViewerFlowMetrics {
  stream_id: string;
  platform: "kick" | "youtube" | "tiktok";
  channel_name?: string;
  is_live?: boolean;
  viewers_current?: number;
  viewers_per_minute?: number;
  viewers_new_estimated?: number;
  viewers_lost_estimated?: number;
  messages_per_minute?: number;
  follows_per_minute?: number;
  engagement_ratio?: number;
  growth_velocity?: number;
  suspicious_growth_score?: number;
  bot_probability?: number;
  trust_score?: number;
  threat_score?: number;
  raid_likelihood?: number;
  suspicious_score?: number;
  active_chatters?: number;
  silent_viewers_estimated?: number;
  ai_flags?: string[];
  updated_at?: string;
}

export interface ViewerFlowTimelinePoint {
  ts: string;
  kind: string;
  label: string;
  value?: number;
  username?: string | null;
  severity?: string;
  metadata?: Record<string, unknown>;
}

export interface SuspiciousViewerFlowRow {
  username: string;
  platform_user_id?: string | null;
  platform: string;
  stream_id: string;
  bot_probability?: number;
  suspicious_score: number;
  trust_score?: number;
  reasons: string[];
  message_count?: number;
  is_silent?: boolean;
  cross_platform_hits?: number;
}

export interface ViewerFlowStreamSnapshot {
  metrics: ViewerFlowMetrics;
  timeline: ViewerFlowTimelinePoint[];
  suspicious_viewers: SuspiciousViewerFlowRow[];
  viewer_history: { t?: string; count?: number }[];
}

export interface ViewerFlowOverview {
  enabled: boolean;
  message?: string;
  tenant_id?: string;
  streams?: ViewerFlowMetrics[];
  global_threat_score?: number;
  active_non_twitch?: number;
  total_suspicious?: number;
  attack_feed?: ViewerFlowTimelinePoint[];
}

export interface PlatformHealthSystem {
  redis_ok?: boolean;
  redis_latency_ms?: number | null;
  realtime_pubsub_ok?: boolean;
  worker_alive?: boolean;
  worker_last_seen?: string | null;
  orchestrator_running?: boolean;
  active_monitors?: number;
  api_process?: string;
}

export interface IntegrationProbe {
  platform: "kick" | "youtube" | "tiktok";
  ok: boolean;
  latency_ms?: number | null;
  circuit_state?: string;
  message?: string;
  checked_at?: string;
}

export interface PlatformHealthStream {
  stream_id: string;
  platform: "kick" | "youtube" | "tiktok";
  channel_name?: string;
  slug?: string;
  status: string;
  is_live?: boolean;
  viewer_count?: number;
  messages_per_min?: number;
  viewers_per_min?: number;
  events_total?: number;
  last_poll_at?: string | null;
  last_event_at?: string | null;
  socket_connected?: boolean;
  socket_transport?: string;
  reconnect_count?: number;
  error_count?: number;
  ai_anomaly_score?: number;
  ai_flags?: string[];
  uptime_seconds?: number;
}

export interface PlatformHealthOverview {
  enabled: boolean;
  message?: string;
  system?: PlatformHealthSystem;
  integrations?: IntegrationProbe[];
  streams?: PlatformHealthStream[];
  issues?: { message?: string; flag?: string; at?: string; severity?: string }[];
  summary?: Record<string, number>;
  updated_at?: string;
}

export interface PlatformMonitorHealthStatus {
  enabled: boolean;
  health_enabled?: boolean;
  running: boolean;
  active_monitors: string[];
  count: number;
  max_streams: number;
  worker_alive?: boolean;
  worker_last_seen?: string | null;
  redis_ok?: boolean;
  redis_latency_ms?: number | null;
}

export interface TwitchBotsOverview {
  enabled: boolean;
  mongodb?: boolean;
  message?: string;
  known_bots_detected?: number;
  total_verifications?: number;
  global_profiles_cached?: number;
  top_bot_types?: { bot_type: string; count: number }[];
  updated_at?: string;
}

export interface TwitchBotsDetection {
  username: string;
  twitch_id?: string;
  bot_type?: string;
  threat_level: "low" | "medium" | "high" | "critical";
  suspicious_score: number;
  stream_id?: string;
  detected_at?: string;
}

export interface LiveStreamSnapshot {
  stream_id: string;
  tenant_id: string;
  platform: string;
  channel_name: string;
  is_live: boolean;
  title?: string;
  viewers: number;
  messages_per_minute: number;
  viewers_per_minute: number;
  follows_per_minute: number;
  engagement_score: number;
  growth_velocity: number;
  organic_engagement_score: number;
  suspicious_activity_score: number;
  synthetic_audience_probability: number;
  live_trust_score: number;
  bot_probability: number;
  viewbot_probability: number;
  suspicious_growth: boolean;
  flags: string[];
}

export interface StreamRankingEntry {
  stream_id: string;
  channel_name: string;
  platform: string;
  rank: number;
  score: number;
  metric: string;
  is_live: boolean;
}

export interface LiveIntelOverview {
  tenant_id: string;
  live_count: number;
  monitored_count: number;
  suspicious_live: number;
  avg_engagement: number;
  rankings_suspicious: StreamRankingEntry[];
  rankings_organic: StreamRankingEntry[];
  rankings_anomaly_growth: StreamRankingEntry[];
  snapshots: LiveStreamSnapshot[];
  heatmap: { stream_id: string; channel: string; platform: string; intensity: number; viewers: number }[];
}

export interface LiveIntelOverviewResponse {
  enabled: boolean;
  overview?: LiveIntelOverview;
}

export interface LiveIntelStreamRow {
  stream_id: string;
  channel_name: string;
  platform: string;
  is_live: boolean;
  viewer_count: number;
  snapshot: LiveStreamSnapshot | null;
}

export interface LiveIntelHistoryPoint {
  ts: string;
  viewers: number;
  engagement_score: number;
  bot_probability: number;
}

export interface StreamComparisonRow {
  stream_id: string;
  channel_name: string;
  platform: string;
  viewers: number;
  messages_per_minute: number;
  engagement_score: number;
  growth_velocity: number;
  bot_probability: number;
}

export interface LiveIntelAnomaly {
  stream_id: string;
  type: string;
  viewbot_probability?: number;
  channel_name?: string;
  created_at?: string;
}

export interface EngagementMetrics {
  stream_id: string;
  viewers_total: number;
  viewers_suspected: number;
  viewers_real_estimate: number;
  engagement_percent: number;
  active_chatters: number;
  unique_chatters: number;
  messages_per_minute: number;
  viewer_to_chat_ratio: number;
  engagement_health_score: number;
  growth_anomaly: boolean;
  lexical_diversity: number;
  synthetic_engagement_score: number;
  updated_at?: string;
}

export interface ThreatGraphNode {
  id: string;
  label: string;
  threat_score: number;
  bot_probability: number;
  platform?: string;
  cluster_id?: number;
}

export interface ThreatGraphEdge {
  source: string;
  target: string;
  weight: number;
  relation: string;
}

export interface ThreatGraphSnapshot {
  stream_id: string;
  nodes: ThreatGraphNode[];
  edges: ThreatGraphEdge[];
  bot_clusters: string[][];
  coordination_score: number;
}

export interface ThreatIntelAssessment {
  entity_key?: string;
  bot_probability: number;
  attack_severity: number;
  coordination_score: number;
  spam_probability: number;
  raid_likelihood: number;
  flags: string[];
  ai_insights: string[];
  engagement?: EngagementMetrics;
  graph?: ThreatGraphSnapshot;
  cross_platform_matches?: CrossPlatformMatch[];
}

export interface ThreatEntitySummary {
  entity_key: string;
  username?: string;
  platform?: string;
  threat_score: number;
  trust_score?: number;
  bot_probability: number;
  engagement_score?: number;
  flags: string[];
}

export interface ThreatIntelOverviewResponse {
  enabled: boolean;
  message?: string;
  global?: { entities: number; high_threat: number; cross_platform: number };
  top_threats?: ThreatEntitySummary[];
}

export interface ThreatIntelStreamResponse {
  stream_id: string;
  cached?: { updated_at: number; assessment: Record<string, unknown> };
  engagement?: EngagementMetrics;
  graph_edge_count: number;
}

export interface CrossPlatformMatch {
  canonical_username: string;
  platforms: string[];
  entity_keys: string[];
  multi_platform: boolean;
}

export interface SocLiveFeedEvent {
  id: string;
  platform: string;
  channel_name: string;
  event_type: string;
  platform_username?: string;
  risk_score: number;
  created_at: string;
  is_proxy?: boolean;
}

export interface AIInsight {
  summary: string;
  severity_assessment: string;
  recommended_action: string;
  recommendation: string;
  confidence: number;
  source: string;
}

export interface AIAssessment {
  risk_score: number;
  attack_probability: number;
  threat_level: string;
  classification: string;
  early_warning: boolean;
  confidence: number;
  false_positive_likelihood: number;
  anomaly_score: number;
  bot_probability: number;
  raid_probability: number;
  viewbot_probability: number;
  automation_probability: number;
  coordination_score: number;
  flags: string[];
  recommended_action: string;
  recommendations: string[];
  auto_mitigate: boolean;
  model_version: string;
  inference_ms: number;
}

export interface AIPredictionEntry {
  stream_id: string;
  channel_name: string;
  platform: string;
  prediction: AIAssessment;
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

export interface SecurityDashboard {
  hours: number;
  stream_id: string | null;
  summary: {
    blocks_429: number;
    blocks_403: number;
    blocks_widget: number;
    blocks_replay: number;
    proxy_detections: number;
    vpn_detections: number;
    tor_detections: number;
    datacenter_detections: number;
    high_risk_events: number;
    automation_signals: number;
    security_attacks: number;
    total_events: number;
  };
  gateway: {
    timeline: { time: string; blocks: number }[];
    top_reasons: { reason: string; count: number }[];
    blocks_429: number;
    blocks_403: number;
    blocks_widget: number;
    blocks_replay: number;
    blocks_payload: number;
  };
  timeline: { time: string; events: number; high_risk: number; proxy: number }[];
  top_flags: { flag: string; count: number }[];
  per_stream: {
    stream_id: string;
    channel_name: string;
    events: number;
    proxy: number;
    vpn: number;
    high_risk: number;
  }[];
  recent_signals: {
    stream_id: string;
    ip_address: string;
    risk_score: number;
    is_proxy: boolean;
    is_vpn: boolean;
    flags: string[];
    created_at: string | null;
  }[];
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
  j48_is_bot?: boolean | null;
  j48_probability?: number | null;
  j48_backend?: string | null;
}

export interface WekaJ48Prediction {
  enabled: boolean;
  session_id?: string | null;
  platform_username?: string | null;
  is_bot: boolean | null;
  probability: number | null;
  class_label?: string | null;
  backend?: string | null;
  error?: string | null;
}
