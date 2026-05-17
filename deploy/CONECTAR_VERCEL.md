# Conectar Vercel (frontend) con tu API

No hace falta cambiar a MongoDB. El frontend ya llama a `/api/*` en el mismo dominio y Vercel reenvía al backend.

```
Navegador  →  https://anti-bots.vercel.app/api/v1/...
                    ↓ (rewrite)
             https://TU-API/api/v1/...  →  Neon (Postgres)
```

WebSockets van **directo** al backend (Vercel no hace proxy de WS).

---

## Opcion A: API en VPS (recomendada)

1. Despliega la API: `deploy\deploy-vps.ps1` (ver `deploy/vps/README.md`).
2. Comprueba: `curl https://api.tudominio.com/health` → `{"status":"healthy",...}`.
3. Configura Vercel (abajo).
4. Redeploy en Vercel.

## Opcion B: API en Render

Guia completa: **[RENDER_VERCEL.md](RENDER_VERCEL.md)**

```powershell
cd deploy
.\deploy-render.ps1
```

1. Pegar env en Render → Save → Manual Deploy  
2. `curl https://anti-bots-api.onrender.com/health`  
3. `.\vercel-conectar.ps1 -ApiUrl "https://anti-bots-api.onrender.com"` → Redeploy Vercel

---

## Variables en Vercel (obligatorio)

Proyecto → **Settings** → **Environment Variables** → **Production**:

| Variable | Valor | Notas |
|----------|--------|--------|
| `API_PROXY_TARGET` | `https://api.tudominio.com` | Sin barra final. URL real de tu API. |
| `NEXT_PUBLIC_WS_URL` | `wss://api.tudominio.com` | Mismo host, esquema `wss`. |

**No pongas** `NEXT_PUBLIC_API_URL=http://localhost:8000` en Production (rompe el dashboard).

Opcional: deja `NEXT_PUBLIC_API_URL` **sin definir** en Production (el codigo usa proxy same-origin).

Desde Windows:

```powershell
cd deploy
.\vercel-conectar.ps1 -ApiUrl "https://api.tudominio.com"
```

Copia al portapapeles y pega en Vercel → **Redeploy**.

---

## Backend (.env en VPS o Render)

Debe incluir:

```env
APP_ENV=production
APP_CORS_ORIGINS=https://anti-bots.vercel.app,https://anti-bots-vhbo.vercel.app
APP_FRONTEND_URL=https://anti-bots.vercel.app
COOKIE_SECURE=true
COOKIE_SAMESITE=none
DATABASE_URL=postgresql+asyncpg://...@neon.../Anti-Bot?sslmode=require
```

Con el **proxy** de Vercel, las cookies de login suelen funcionar en same-origin (`vercel.app/api/...`).

---

## Comprobar que todo funciona

1. Abre `https://anti-bots.vercel.app`
2. Login con tu usuario Neon (`nelsondavid1954@gmail.com` si lo importaste)
3. DevTools → Network: peticiones a `/api/v1/...` con status **200** (no 404/502)
4. Dashboard: indicador WebSocket conectado (requiere `NEXT_PUBLIC_WS_URL` correcto)

| Sintoma | Causa probable |
|---------|----------------|
| 502 en `/api/*` | API caida o `API_PROXY_TARGET` mal |
| 404 en `/api/*` | API no desplegada |
| Login falla / 401 | `DATABASE_URL` o secretos mal en el backend |
| WS desconectado | Falta `NEXT_PUBLIC_WS_URL` o firewall del VPS (puerto 443) |
| CORS error | `APP_CORS_ORIGINS` sin tu dominio Vercel |

---

## Arquitectura viable (resumen)

| Pieza | Donde | Coste aprox. |
|-------|--------|----------------|
| Frontend | Vercel | Gratis |
| API | VPS + Docker o Render | 0–6 USD/mes |
| Base de datos | Neon Postgres | Gratis tier |

MongoDB **no es necesario** para conectar Vercel; Postgres + Neon ya encaja con el codigo actual.
