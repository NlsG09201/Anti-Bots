# Render (API) + Vercel (frontend)

## Checklist rapido

- [ ] **1.** Importar env en Render (28 variables)
- [ ] **2.** Manual Deploy en Render
- [ ] **3.** Log: `Preflight OK — starting uvicorn`
- [ ] **4.** `curl https://anti-bots.onrender.com/health` → healthy
- [ ] **5.** Variables en Vercel (`API_PROXY_TARGET`, `NEXT_PUBLIC_API_DIRECT_URL`, `NEXT_PUBLIC_WS_URL`)
- [ ] **6.** Redeploy Vercel
- [ ] **7.** Login en https://anti-bots.vercel.app

---

## Paso 1 — Variables en Render (obligatorio)

En Windows:

```powershell
cd deploy
.\deploy-render.ps1
```

O solo import manual:

```powershell
.\import-render-manual.ps1
```

En [dashboard.render.com](https://dashboard.render.com):

1. Servicio **anti-bots-api**
2. **Environment** → **Add from .env** → Ctrl+V → **Save Changes**
3. Verifica que existan (valor oculto): `DATABASE_URL`, `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `AES_ENCRYPTION_KEY`

Sin esto veras: `Variables NO definidas: DATABASE_URL` y **Exited with status 1**.

**MongoDB Atlas (opcional):** si `MONGODB_URI` falla con SSL (`TLSV1_ALERT_INTERNAL_ERROR`), la API **sigue arrancando** (sin persistencia Mongo). Corrige en Atlas: Network Access `0.0.0.0/0`, URI `mongodb+srv://...`, contraseña **URL-encoded**, usuario con permisos readWrite.

---

## Paso 2 — Start Command

**Settings** → **Start Command**:

- Dejalo **vacío** (usa `render.yaml`), **o** exactamente:

```bash
python scripts/render_check_env.py && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Si solo dice `uvicorn app.main:app...` sin preflight, actualiza desde GitHub o pega el comando de arriba.

---

## Paso 3 — Deploy

**Manual Deploy** → espera build + deploy (3–8 min en free tier).

**Logs** (runtime, no solo build):

```
StreamShield preflight — APP_ENV=production render=True ...
Preflight OK — starting uvicorn
startup_checks_passed
```

---

## Recuperacion de errores 401 en la aplicacion

Si `/api/v1/streams` o `/viewers` responde 401 despues de iniciar sesion:

1. Cierra sesion e inicia de nuevo desde Vercel para emitir un token nuevo. El cliente intenta renovarlo una sola vez mediante la cookie HttpOnly y el proxy `/api`; nunca copies ni compartas Bearer tokens o cookies.
2. Comprueba `/api/v1/auth/me` desde la misma sesion. Si devuelve 200 y otra ruta protegida falla, revisa los logs del mismo despliegue de Render y que las URLs directa y proxy apunten al mismo API.
3. Confirma en Render que todas las instancias API usan el mismo `JWT_SECRET_KEY`. Rotarlo invalida los access y refresh tokens previos; los usuarios deben iniciar sesion otra vez.
4. Redepliega Vercel para servir el cliente actualizado y confirma `API_PROXY_TARGET` y `NEXT_PUBLIC_API_DIRECT_URL`.
5. Si el login nuevo sigue fallando, compara el status y mensaje sanitizado de `/api/v1/auth/me` con los logs de Render. No compartas tokens, cookies, contraseñas ni valores de secretos.

El backend registra `authentication_rejected` junto con una causa acotada (`missing_or_malformed_authorization`, `access_token_expired`, `access_token_invalid_signature_or_malformed`, `access_token_invalid_claims`, `access_token_wrong_token_type`, `revoked_access_token`, `invalid_subject_claim` o `user_missing_or_inactive`) y la ruta. Estos eventos no incluyen bearer, cookies ni identificadores de usuario. `access_token_invalid_signature_or_malformed` tras un login nuevo apunta a revisar que todas las instancias usen el mismo `JWT_SECRET_KEY`. Úsalos en Logs de Render para separar un cliente sin credenciales de un token vencido, una firma no válida, revocación o cuenta inactiva.

Un 401 en el dominio directo de Render y en el rewrite de Vercel no prueba que exista un problema de CORS: ambos caminos pueden estar enviando un Bearer rechazado por el API.

## SOC multi-plataforma (Kick / YouTube / TikTok)

Variables recomendadas en Render:

| Variable | Uso |
|----------|-----|
| `REDIS_URL` | URL nativa Redis `redis://`/`rediss://` de Upstash; necesaria para arq, Redis Streams y pub/sub del WebSocket |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Credenciales REST HTTPS; habilitan cache compartida para auth, rate limits y datos cacheados. Configura ambas en Render para API y worker. |
| `YOUTUBE_API_KEY` | Live chat + viewers YouTube Data API v3 |
| `PLATFORM_MONITOR_ENABLED` | `true` — monitores en el proceso API (max 12 streams) |
| `PLATFORM_MONITOR_MAX_STREAMS` | Límite RAM/CPU en free tier (default `12`) |
| `TIKTOK_SESSION_ID` | Opcional si TikTok bloquea conexiones |

En el dashboard: **Channels** → plataforma Kick/YouTube/TikTok → slug del canal → **Escanear** cuando esté LIVE.

El backend usa el par REST HTTPS para operaciones de cache (`GET`, `SET`, `DEL`, `INCR`, `EXISTS`). Las credenciales REST no sustituyen `REDIS_URL`: el worker `arq` y los flujos de Redis TCP consumen el protocolo Redis nativo. En Upstash copia `Redis URL`/`Redis connection string` para `REDIS_URL` y, por separado, el HTTPS URL y token REST para las dos variables REST. No publiques estos valores en Git ni los pegues en logs.

En un Blueprint existente, Render no vuelve a pedir automáticamente valores para nuevas variables `sync: false`; añádelas manualmente al servicio `anti-bots-api` y a `anti-bots-platform-monitor` desde **Environment**. Usa las credenciales REST que compartiste para sus variables respectivas. Para habilitar colas `arq`, Redis Streams y pub/sub del WebSocket, añade además la URL nativa TLS de Upstash como `REDIS_URL`. Si sólo configuras REST, el cache funciona por HTTPS y el worker omite arq sin dejar de ejecutar el monitor de plataformas.

Endpoints SOC: `GET /api/v1/soc/overview`, `GET /api/v1/soc/feed`.

### TwitchBots.info (directorio publico de bots)

| Variable | Uso |
|----------|-----|
| `TWITCHBOTS_INFO_ENABLED` | `true` — verificacion contra api.twitchbots.info/v2 |
| `TWITCHBOTS_INFO_VERIFY_ON_INGEST` | Verificar cada viewer al ingestar |
| `TWITCHBOTS_INFO_QUEUE_ENABLED` | Lotes grandes via worker arq (`REDIS_URL` requerido) |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Resolver username → Twitch ID (Helix) |

Endpoints: `GET /api/v1/twitchbots/overview`, `GET /api/v1/twitchbots/detections`, `POST /api/v1/twitchbots/verify`, `POST /api/v1/twitchbots/verify/batch`.

Panel en **SOC Command** → *Bots conocidos (TwitchBots.info)*. Evento WebSocket: `twitchbots_detection`.

### Salud monitores multi-plataforma

| Variable | Uso |
|----------|-----|
| `PLATFORM_HEALTH_ENABLED` | Motor de auditoría cada 45s (API + worker) |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Heartbeat worker y caché de salud mediante REST |
| `REDIS_URL` | Pub/Sub `platform_monitor_health` y colas arq |
| `PLATFORM_MONITOR_RUN_IN_API` | `false` en API si usas worker dedicado |
| `PLATFORM_MONITOR_WORKER` | `true` en servicio `anti-bots-platform-monitor` |

Endpoints: `GET /api/v1/platform-health/overview`, `POST /api/v1/platform-health/audit`, `GET /api/v1/platform-health/integrations`.

Panel SOC: **Salud monitores (Kick / YouTube / TikTok)**. WebSocket: `platform_monitor_health`.

### Worker dedicado (`anti-bots-platform-monitor`)

El Blueprint `render.yaml` define un **background worker** con `Dockerfile.worker` (sin JVM Weka).

1. En Render, el worker debe tener **las mismas variables** que el API (`DATABASE_URL`, `REDIS_URL`, OAuth keys, etc.).
2. Importa env en **ambos** servicios desde `deploy/render.env`.
3. En Kick Developer Console y Google Cloud, registra:
   - `https://anti-bots.onrender.com/api/v1/integrations/kick/callback`
   - `https://anti-bots.onrender.com/api/v1/integrations/youtube/callback`
4. **Settings** en el dashboard → Conectar Kick / YouTube.

OAuth Kick usa **PKCE (S256)** obligatorio.

---

## Paso 4 — Probar API

```powershell
curl https://anti-bots.onrender.com/health
```

Respuesta esperada:

```json
{"status":"healthy","service":"StreamShield","version":"1.0.0"}
```

---

## Paso 5 — Vercel

```powershell
.\vercel-conectar.ps1 -ApiUrl "https://anti-bots.onrender.com"
```

Pega en Vercel → **Environment Variables** → **Production**:

| Variable | Valor |
|----------|--------|
| `API_PROXY_TARGET` | `https://anti-bots.onrender.com` |
| `NEXT_PUBLIC_API_DIRECT_URL` | `https://anti-bots.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://anti-bots.onrender.com` |

Las llamadas con Bearer usan Render directamente. Login, registro, logout y renovaciÃ³n
siguen usando el proxy para conservar las cookies HttpOnly. Configura la URL en Vercel,
no en `render.env`, y aplica la variable a Production y Preview si usas ambos entornos.

Elimina `NEXT_PUBLIC_API_URL` si es `localhost`.

**Deployments** → **Redeploy**.

---

## Paso 6 — Neon

Si usas IP allowlist en Neon, permite salida de Render (o desactiva allowlist para pruebas).

Render outbound (referencia): `74.220.49.0/24`, `74.220.57.0/24`

---

## Paso 7 — Twitch (cuando la API viva)

En [dev.twitch.tv](https://dev.twitch.tv):

- Redirect: `https://anti-bots.onrender.com/api/v1/integrations/twitch/callback`
- EventSub: `https://anti-bots.onrender.com/api/v1/webhooks/twitch`

---

## Problemas frecuentes

| Error | Solucion |
|-------|----------|
| `Exited with status 1` sin mas texto | Importar `render.import.env` completo |
| `Variables NO definidas` | Save en Environment, redeploy |
| Solo `Running uvicorn...` sin preflight | Corregir Start Command |
| Vercel 502 en `/api/*` | API caida; revisar Render logs |
| WS desconectado | `NEXT_PUBLIC_WS_URL=wss://anti-bots.onrender.com` |
| Cold start 50s | Normal en free tier; espera y recarga |

---

## Automatizar env (opcional)

Con API key `rnd_...` de Render:

```powershell
.\push-render-env.ps1
```

No uses `1` como clave; debe empezar por `rnd_`.

---

## Threat Intelligence Engine (MongoDB + Redis)

Para la base global de amenazas, engagement health y grafos:

| Variable | Servicio | Notas |
|----------|----------|-------|
| `MONGODB_URI` | API + worker | Atlas connection string (`mongodb+srv://...`) |
| `REDIS_URL` | API + worker | Upstash TLS URL (pub/sub TI + SOC) |
| `THREAT_INTEL_ENGINE_ENABLED` | API | `true` (default) |

Colecciones MongoDB (auto-index en startup): `threat_entities`, `cross_platform_links`, `engagement_metrics`, `chat_patterns`, `ai_predictions`, `graph_edges`.

API: `/api/v1/streaming-intelligence/*`  
Dashboard: `/dashboard/threat-intelligence` (Cytoscape + engagement en vivo vía WebSocket `threat_intel_update`).

## Live Stream Intelligence Monitor

Monitoreo competitivo de streams externos (Kick, YouTube, TikTok, Twitch):

| Variable | Default | Descripción |
|----------|---------|-------------|
| `LIVE_INTEL_ENABLED` | `true` | Sampler de métricas públicas |
| `LIVE_INTEL_SAMPLE_SECONDS` | `20` | Intervalo de muestreo |
| `LIVE_INTEL_MAX_STREAMS` | `30` | Máximo de canales competitivos |

Al usar **Channels → Watch**, se activa `competitive_intel` automáticamente.

API: `/api/v1/live-intelligence/*`  
Dashboard: `/dashboard/live-intelligence`  
WebSocket: `live_intel_update`
