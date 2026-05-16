# Despliegue en Vercel (ya tienes cuenta)

## Paso 1 — Subir código a GitHub

Vercel necesita un repositorio Git. En PowerShell:

```powershell
cd "C:\Users\nelso\OneDrive\Escritorio\Anti-Bots"
git init
git add .
git commit -m "StreamShield - deploy inicial"
git branch -M main
```

Crea repo en https://github.com/new (sin README), luego:

```powershell
git remote add origin https://github.com/TU_USUARIO/TU-REPO.git
git push -u origin main
```

> No se sube `.env` (está en `.gitignore`).

---

## Paso 2 — Importar en Vercel

1. [vercel.com/dashboard](https://vercel.com/dashboard) → **Add New…** → **Project**
2. **Import** tu repositorio de GitHub
3. Configuración importante:

| Campo | Valor |
|-------|--------|
| **Root Directory** | `frontend` ← clic en Edit, escribe `frontend` |
| Framework | Next.js (auto) |
| Build Command | `npm run build` |
| Output | default |

4. **Environment Variables** (por ahora, si aún no tienes API):

```
NEXT_PUBLIC_API_URL = http://localhost:8000
NEXT_PUBLIC_WS_URL = ws://localhost:8000
```

Cambia esto cuando tengas Render (paso 4).

5. **Deploy** → espera 2–3 minutos
6. Copia tu URL: `https://tu-proyecto.vercel.app`

---

## Paso 3 — Backend en Render (necesario para que funcione el login)

El frontend en Vercel **solo muestra la UI**. El login y datos vienen de la API.

1. [render.com](https://render.com) → Sign up con GitHub
2. **New +** → **Web Service** → mismo repo
3. **Root Directory:** `backend`
4. **Build:** `pip install -r requirements.txt`
5. **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Variables mínimas:

```
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<genera uno>
JWT_SECRET_KEY=<genera otro>
AES_ENCRYPTION_KEY=<32 caracteres>
DATABASE_URL=<de neon.tech - ver abajo>
REDIS_URL=<de upstash.com>
CELERY_BROKER_URL=<misma redis>
CELERY_RESULT_BACKEND=<misma redis>
COOKIE_SECURE=true
COOKIE_SAMESITE=strict
```

7. URL API: `https://tu-servicio.onrender.com`

**Neon (DB gratis):** https://neon.tech → connection string → `DATABASE_URL`  
**Upstash (Redis gratis):** https://upstash.com → Redis URL

---

## Paso 4 — Conectar Vercel con Render

En **Vercel** → tu proyecto → **Settings** → **Environment Variables**:

```
NEXT_PUBLIC_API_URL = https://tu-servicio.onrender.com
NEXT_PUBLIC_WS_URL = wss://tu-servicio.onrender.com
```

**Deployments** → los tres puntos del último deploy → **Redeploy**

En **Render** → Environment:

```
APP_CORS_ORIGINS=https://tu-proyecto.vercel.app
APP_FRONTEND_URL=https://tu-proyecto.vercel.app
TRUSTED_HOSTS=tu-servicio.onrender.com
```

Guarda → Render redespliega.

---

## Paso 5 — Probar

1. Abre `https://tu-proyecto.vercel.app`
2. Crear cuenta → debe funcionar si la API en Render está **Live**
3. Primera petición a Render free puede tardar ~60 s (cold start)

---

## Orden recomendado si vas paso a paso

1. ✅ Vercel (cuenta creada)
2. GitHub (subir repo)
3. Vercel deploy (frontend)
4. Neon + Upstash
5. Render (API)
6. Actualizar variables Vercel + Render
7. Twitch en Settings (opcional)
