# Despliegue paso a paso — StreamShield

Guía para publicar la app en internet **con dominio propio** o **sin comprar dominio** (URLs gratuitas de Vercel y Render).

---

## ¿Necesito un dominio?

| Opción | Coste | URL ejemplo | ¿Sirve para producción? |
|--------|-------|-------------|-------------------------|
| **Sin dominio** | $0 | `streamshield.vercel.app` + `streamshield-api.onrender.com` | Sí, para empezar y pruebas |
| **Dominio propio** | ~$10/año | `app.tudominio.com` | Sí, más profesional |
| **Dominio + Cloudflare** | ~$10/año | Igual + WAF gratis | Recomendado cuando crezcas |

Twitch, OAuth y HTTPS funcionan con URLs de Vercel/Render (ya traen HTTPS).

---

# RUTA A — Sin dominio (100% gratis)

Usarás dos URLs que te regalan los proveedores:

- **Frontend:** `https://TU-PROYECTO.vercel.app`
- **API:** `https://TU-SERVICIO.onrender.com`

Anota estas URLs cuando las tengas; las usarás en varios pasos.

---

## Paso 1 — Cuenta en GitHub

1. Crea cuenta en [github.com](https://github.com).
2. Crea repositorio nuevo (público o privado).
3. Sube el proyecto:

```powershell
cd "C:\Users\nelso\OneDrive\Escritorio\Anti-Bots"
git init
git add .
git commit -m "StreamShield initial"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/streamshield.git
git push -u origin main
```

---

## Paso 2 — Base de datos (Neon) — gratis

1. Entra en [neon.tech](https://neon.tech) → Sign up.
2. **New Project** → elige región cercana (ej. `us-east-1`).
3. Copia la connection string **pooled** con asyncpg:

```
postgresql+asyncpg://usuario:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require
```

4. Guárdala como `DATABASE_URL` (la pegarás en Render).

---

## Paso 3 — Redis (Upstash) — gratis

1. Entra en [upstash.com](https://upstash.com) → Create database.
2. Tipo: Regional, TLS activado.
3. Copia la URL Redis (formato `rediss://...`).
4. Usarás la misma URL para:
   - `REDIS_URL`
   - `CELERY_BROKER_URL`
   - `CELERY_RESULT_BACKEND`

---

## Paso 4 — Generar secretos

En PowerShell (guarda el resultado en un bloc de notas seguro):

```powershell
# Repite 3 veces para 3 secretos distintos
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

Necesitas:
- `APP_SECRET_KEY`
- `JWT_SECRET_KEY`
- `AES_ENCRYPTION_KEY` (32+ caracteres)

---

## Paso 5 — API en Render (backend)

1. [render.com](https://render.com) → Sign up → conecta GitHub.
2. **New +** → **Web Service** → selecciona tu repo.
3. Configuración:

| Campo | Valor |
|-------|-------|
| Name | `streamshield-api` |
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Plan | Free |

4. **Environment Variables** (pega todas):

```env
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<tu secreto 1>
JWT_SECRET_KEY=<tu secreto 2>
AES_ENCRYPTION_KEY=<tu secreto 3>
DATABASE_URL=<neon connection string>
REDIS_URL=<upstash rediss url>
CELERY_BROKER_URL=<misma upstash url>
CELERY_RESULT_BACKEND=<misma upstash url>
COOKIE_SECURE=true
COOKIE_SAMESITE=strict
```

Deja `APP_CORS_ORIGINS` y `APP_FRONTEND_URL` vacíos por ahora (las añades después de Vercel).

5. **Create Web Service** → espera el deploy.
6. Copia la URL: `https://streamshield-api.onrender.com` (la tuya será distinta).

7. Prueba: abre `https://TU-API.onrender.com/health` → debe decir `"status":"healthy"`.

> **Nota free tier:** Render “duerme” la API tras ~15 min sin tráfico. La primera petición tarda 30–60 s.

---

## Paso 6 — Frontend en Vercel

1. [vercel.com](https://vercel.com) → Sign up → Import Git Repository.
2. Selecciona el mismo repo.
3. Configuración:

| Campo | Valor |
|-------|-------|
| Framework Preset | Next.js |
| Root Directory | `frontend` |

4. **Environment Variables:**

```env
NEXT_PUBLIC_API_URL=https://TU-API.onrender.com
NEXT_PUBLIC_WS_URL=wss://TU-API.onrender.com
```

5. **Deploy** → copia la URL: `https://tu-proyecto.vercel.app`.

---

## Paso 7 — Conectar frontend y backend (CORS)

Vuelve a **Render** → tu servicio → **Environment** → añade/actualiza:

```env
APP_CORS_ORIGINS=https://tu-proyecto.vercel.app
APP_FRONTEND_URL=https://tu-proyecto.vercel.app
TRUSTED_HOSTS=tu-api.onrender.com
```

Guarda → Render redespliega solo.

En **Vercel** → Settings → Environment Variables: confirma que `NEXT_PUBLIC_API_URL` apunta a tu API.

**Redeploy** Vercel si cambiaste variables.

---

## Paso 8 — Twitch (opcional pero recomendado)

1. [dev.twitch.tv/console](https://dev.twitch.tv/console) → Register Your Application.
2. OAuth Redirect URL (exacta):

```
https://TU-API.onrender.com/api/v1/integrations/twitch/callback
```

3. En Render, añade:

```env
TWITCH_CLIENT_ID=<de twitch>
TWITCH_CLIENT_SECRET=<de twitch>
TWITCH_REDIRECT_URI=https://TU-API.onrender.com/api/v1/integrations/twitch/callback
TWITCH_EVENTSUB_CALLBACK_URL=https://TU-API.onrender.com/api/v1/webhooks/twitch
TWITCH_WEBHOOK_SECRET=<string aleatorio 32+ chars>
APP_FRONTEND_URL=https://tu-proyecto.vercel.app
```

4. En la app: **Settings → Conectar con Twitch**.

---

## Paso 9 — Threat intel (opcional)

En Render:

```env
ABUSEIPDB_API_KEY=<de abuseipdb.com>
IPQUALITYSCORE_API_KEY=<de ipqualityscore.com>
DISCORD_WEBHOOK_URL=<webhook de discord>
```

---

## Paso 10 — Probar en producción

1. Abre `https://tu-proyecto.vercel.app`
2. Crea cuenta → entra al dashboard
3. Ve a **Deploy** en el menú → marca el checklist
4. Verifica `/docs` en la API → debe dar **404** (seguridad OK)

---

# RUTA B — Con dominio propio

Si compras un dominio (Namecheap, Cloudflare Registrar, Google Domains, etc.):

## Paso extra 1 — Cloudflare DNS

1. Añade el sitio en [dash.cloudflare.com](https://dash.cloudflare.com).
2. Cambia los nameservers en tu registrador a los de Cloudflare.
3. Crea registros DNS:

| Tipo | Nombre | Destino |
|------|--------|---------|
| CNAME | `app` | `cname.vercel-dns.com` (Vercel te da el exacto) |
| CNAME | `api` | `TU-SERVICIO.onrender.com` |

En Vercel: Settings → Domains → añade `app.tudominio.com`.  
En Render: Settings → Custom Domains → añade `api.tudominio.com`.

## Paso extra 2 — Actualizar variables

```env
APP_CORS_ORIGINS=https://app.tudominio.com
APP_FRONTEND_URL=https://app.tudominio.com
TRUSTED_HOSTS=api.tudominio.com,app.tudominio.com
NEXT_PUBLIC_API_URL=https://api.tudominio.com
NEXT_PUBLIC_WS_URL=wss://api.tudominio.com
TWITCH_REDIRECT_URI=https://api.tudominio.com/api/v1/integrations/twitch/callback
```

Activa en Cloudflare: SSL Full (strict), Always HTTPS, Bot Fight Mode.

---

# Worker Celery (opcional en free tier)

Render free permite **un** servicio web gratis. Para workers:

**Opción 1:** Omitir Celery al inicio (detección síncrona en la API funciona).

**Opción 2:** Segundo servicio Background Worker en Render (de pago ~$7/mes).

**Opción 3:** Oracle Cloud Free VM + `docker-compose.cloud.yml` (siempre encendido, $0).

---

# Resumen visual del flujo

```
Usuario → vercel.app (frontend)
              ↓ API calls
         onrender.com (backend)
              ↓
    Neon (Postgres) + Upstash (Redis)
              ↓
    Twitch EventSub / AbuseIPDB
```

---

# Problemas frecuentes

| Problema | Solución |
|----------|----------|
| CORS error en login | `APP_CORS_ORIGINS` debe ser exactamente la URL de Vercel (con `https`, sin `/` final) |
| API lenta al primer acceso | Normal en Render free (cold start) |
| Twitch OAuth falla | Redirect URI debe coincidir **carácter por carácter** con Twitch Console |
| Cookies no funcionan | `COOKIE_SECURE=true` solo con HTTPS (Vercel/Render ya lo tienen) |
| WebSocket no conecta | Usa `wss://` en `NEXT_PUBLIC_WS_URL` |

---

# Checklist en la app

Abre tu app desplegada → menú **Deploy** → marca cada paso (se guarda en el navegador).

Documentación relacionada:
- [DEPLOYMENT_FREE.md](./DEPLOYMENT_FREE.md) — detalle de seguridad
- [PRODUCTION.md](./PRODUCTION.md) — variables de producción
