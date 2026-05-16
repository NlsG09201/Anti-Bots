# Despliegue gratuito en la nube (StreamShield)

Guía para desplegar sin coste inicial y con el menor riesgo posible.

## Arquitectura recomendada (tier gratuito)

| Componente | Servicio gratuito | Límite típico |
|------------|-------------------|---------------|
| Frontend | [Vercel](https://vercel.com) | 100 GB bandwidth/mes |
| API Backend | [Render](https://render.com) o [Fly.io](https://fly.io) | 750 h/mes (Render) |
| PostgreSQL | [Neon](https://neon.tech) | 0.5 GB, compute limitado |
| Redis | [Upstash](https://upstash.com) | 10k comandos/día |
| Cola Celery | Redis como broker (sin RabbitMQ) | Incluido en Upstash |
| CDN + WAF | [Cloudflare](https://cloudflare.com) | Plan Free |
| Dominio | Cloudflare / Freenom / comprado | — |
| Alertas | Discord Webhook | Gratis |

**Nota:** El plan gratuito de Render duerme la API tras inactividad (~15 s cold start). Para producción seria considera un VPS en Oracle Cloud Free Tier (siempre encendido).

---

## Paso 1: Dominio y Cloudflare (obligatorio para seguridad)

1. Registra un dominio o usa uno existente.
2. Añade el sitio en Cloudflare (plan Free).
3. Activa:
   - **SSL/TLS** → Full (strict)
   - **Always Use HTTPS**
   - **Security** → WAF managed rules (free)
   - **Bot Fight Mode** (free)
   - **Rate limiting** básico en `/api/*` (5-10 req/s por IP)
4. Crea registro DNS:
   - `app.tudominio.com` → Vercel (frontend)
   - `api.tudominio.com` → Render/Fly (backend)

Obtén en Cloudflare:
- `CLOUDFLARE_ZONE_ID` (Overview del dominio)
- `CLOUDFLARE_API_TOKEN` (API Tokens → template "Edit zone DNS" + Firewall si usas auto-block)

---

## Paso 2: Base de datos (Neon)

1. Crea proyecto en [neon.tech](https://neon.tech).
2. Copia connection string **pooled** (async):
   ```
   postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```
3. Variable: `DATABASE_URL`

---

## Paso 3: Redis (Upstash)

1. Crea base Redis en [upstash.com](https://upstash.com).
2. Copia URL:
   ```
   REDIS_URL=rediss://default:TOKEN@xxx.upstash.io:6379
   CELERY_BROKER_URL=rediss://default:TOKEN@xxx.upstash.io:6379
   CELERY_RESULT_BACKEND=rediss://default:TOKEN@xxx.upstash.io:6379
   ```
   Usar Redis como broker evita pagar RabbitMQ.

---

## Paso 4: Secretos de aplicación

Genera valores únicos (PowerShell):

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

Configura en Render/Vercel (Environment Variables):

```
APP_ENV=production
APP_DEBUG=false
COOKIE_SECURE=true
COOKIE_SAMESITE=strict
APP_CORS_ORIGINS=https://app.tudominio.com
TRUSTED_HOSTS=api.tudominio.com,tudominio.com
APP_SECRET_KEY=<generado>
JWT_SECRET_KEY=<generado>
AES_ENCRYPTION_KEY=<32 bytes generado>
```

---

## Paso 5: API en Render

1. Conecta repositorio GitHub.
2. **New Web Service** → Root: `backend`
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Añade todas las variables de `.env.example`.
6. Health check path: `/health`

Worker Celery (opcional en free tier — mismo repo, otro service):
- Start: `celery -A app.workers.celery_app worker --loglevel=info`

---

## Paso 6: Frontend en Vercel

1. Importa repo, root: `frontend`
2. Variables:
   ```
   NEXT_PUBLIC_API_URL=https://api.tudominio.com
   NEXT_PUBLIC_WS_URL=wss://api.tudominio.com
   ```
3. Deploy automático en cada push.

---

## Paso 7: APIs externas (mínimo viable)

| Key | Dónde | Gratis |
|-----|-------|--------|
| AbuseIPDB | abuseipdb.com/account/api | 1000 req/día |
| IPQualityScore | ipqualityscore.com | Trial limitado |
| Twitch | dev.twitch.tv/console | Gratis |
| Discord webhook | Discord canal | Gratis |

`TWITCH_EVENTSUB_CALLBACK_URL=https://api.tudominio.com/api/v1/webhooks/twitch`

---

## Checklist anti-vulnerabilidades en la nube

### Red y perímetro
- [ ] API solo accesible vía Cloudflare (oculta IP real de Render si es posible)
- [ ] Postgres y Redis **sin acceso público** (solo desde backend)
- [ ] No expongas puertos 5432, 6379, 5672 a internet

### Aplicación (ya en código)
- [x] Refresh token en cookie HttpOnly
- [x] Access token solo en memoria (no localStorage)
- [x] CSRF en producción
- [x] Brute-force login lockout
- [x] Rate limiting distribuido
- [x] Validación de secretos al arrancar en `APP_ENV=production`
- [x] Swagger deshabilitado en producción
- [x] TrustedHost middleware

### Configuración obligatoria producción
- [ ] `APP_ENV=production`
- [ ] `APP_DEBUG=false`
- [ ] `COOKIE_SECURE=true`
- [ ] `COOKIE_SAMESITE=strict`
- [ ] CORS solo tu dominio frontend
- [ ] Secretos distintos entre entornos

### Operaciones
- [ ] Rotar keys cada 90 días
- [ ] Backups Neon (automáticos en plan paid; export manual en free)
- [ ] Monitorear logs Render + alertas Discord
- [ ] No commitear `.env`

---

## Qué falta para tier gratuito completo

| Funcionalidad | Estado | Alternativa free |
|---------------|--------|------------------|
| RabbitMQ dedicado | Opcional | Redis como broker (configurado) |
| Grafana/Prometheus 24/7 | Pesado en free | Logs Render + UptimeRobot free |
| MaxMind GeoIP | Requiere descarga | IPQualityScore cubre geo |
| Workers Celery siempre on | 2º servicio Render | Procesar sync en API o cron externo |
| MFA admin | No implementado | Añadir en v2 |

---

## Oracle Cloud Free Tier (alternativa 24/7)

Si necesitas servidor siempre activo sin cold start:

1. VM ARM Ampere (4 OCPU, 24 GB RAM gratis).
2. Instala Docker + docker compose.
3. Usa `docker-compose.yml` del repo con `.env` producción.
4. NGINX + Let's Encrypt (Certbot) delante.
5. Cloudflare proxy naranja activado.

Más trabajo de mantenimiento, pero $0/mes y sin sleep.

---

## Verificación post-deploy

```bash
curl https://api.tudominio.com/health
# Debe devolver {"status":"healthy",...}

# Docs NO deben estar públicos en producción:
curl -I https://api.tudominio.com/docs
# Debe ser 404
```

Registra un usuario en `https://app.tudominio.com` y verifica login + dashboard.
