# Render (API) + Vercel (frontend)

## Checklist rapido

- [ ] **1.** Importar env en Render (28 variables)
- [ ] **2.** Manual Deploy en Render
- [ ] **3.** Log: `Preflight OK — starting uvicorn`
- [ ] **4.** `curl https://anti-bots-api.onrender.com/health` → healthy
- [ ] **5.** Variables en Vercel (`API_PROXY_TARGET`, `NEXT_PUBLIC_WS_URL`)
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

## SOC multi-plataforma (Kick / YouTube / TikTok)

Variables recomendadas en Render:

| Variable | Uso |
|----------|-----|
| `REDIS_URL` | Upstash `rediss://` — pub/sub WebSocket + cola eventos |
| `YOUTUBE_API_KEY` | Live chat + viewers YouTube Data API v3 |
| `PLATFORM_MONITOR_ENABLED` | `true` — monitores en el proceso API (max 12 streams) |
| `PLATFORM_MONITOR_MAX_STREAMS` | Límite RAM/CPU en free tier (default `12`) |
| `TIKTOK_SESSION_ID` | Opcional si TikTok bloquea conexiones |

En el dashboard: **Channels** → plataforma Kick/YouTube/TikTok → slug del canal → **Escanear** cuando esté LIVE.

Endpoints SOC: `GET /api/v1/soc/overview`, `GET /api/v1/soc/feed`.

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
curl https://anti-bots-api.onrender.com/health
```

Respuesta esperada:

```json
{"status":"healthy","service":"StreamShield","version":"1.0.0"}
```

---

## Paso 5 — Vercel

```powershell
.\vercel-conectar.ps1 -ApiUrl "https://anti-bots-api.onrender.com"
```

Pega en Vercel → **Environment Variables** → **Production**:

| Variable | Valor |
|----------|--------|
| `API_PROXY_TARGET` | `https://anti-bots-api.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://anti-bots-api.onrender.com` |

Elimina `NEXT_PUBLIC_API_URL` si es `localhost`.

**Deployments** → **Redeploy**.

---

## Paso 6 — Neon

Si usas IP allowlist en Neon, permite salida de Render (o desactiva allowlist para pruebas).

Render outbound (referencia): `74.220.49.0/24`, `74.220.57.0/24`

---

## Paso 7 — Twitch (cuando la API viva)

En [dev.twitch.tv](https://dev.twitch.tv):

- Redirect: `https://anti-bots-api.onrender.com/api/v1/integrations/twitch/callback`
- EventSub: `https://anti-bots-api.onrender.com/api/v1/webhooks/twitch`

---

## Problemas frecuentes

| Error | Solucion |
|-------|----------|
| `Exited with status 1` sin mas texto | Importar `render.import.env` completo |
| `Variables NO definidas` | Save en Environment, redeploy |
| Solo `Running uvicorn...` sin preflight | Corregir Start Command |
| Vercel 502 en `/api/*` | API caida; revisar Render logs |
| WS desconectado | `NEXT_PUBLIC_WS_URL=wss://anti-bots-api.onrender.com` |
| Cold start 50s | Normal en free tier; espera y recarga |

---

## Automatizar env (opcional)

Con API key `rnd_...` de Render:

```powershell
.\push-render-env.ps1
```

No uses `1` como clave; debe empezar por `rnd_`.
