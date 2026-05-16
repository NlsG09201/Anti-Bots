# Checklist de despliegue

Usa el checklist interactivo en el dashboard: **Deploy** (guarda progreso en localStorage).

O marca manualmente:

## Fase 1 — Infraestructura
- [ ] Dominio + Cloudflare (SSL Full strict, HTTPS, WAF)
- [ ] Neon PostgreSQL (`DATABASE_URL` con SSL)
- [ ] Upstash Redis (`REDIS_URL`, `CELERY_BROKER_URL`)

## Fase 2 — Aplicación
- [ ] Render/Fly: API con `APP_ENV=production`
- [ ] Vercel: frontend con URLs públicas
- [ ] Secretos únicos (APP/JWT/AES)
- [ ] `COOKIE_SECURE=true`, CORS y TRUSTED_HOSTS

## Fase 3 — Twitch
- [ ] [dev.twitch.tv/console](https://dev.twitch.tv/console) — Client ID/Secret
- [ ] Redirect: `https://api.TUDOMINIO.com/api/v1/integrations/twitch/callback`
- [ ] EventSub: `TWITCH_EVENTSUB_CALLBACK_URL` + `TWITCH_WEBHOOK_SECRET`
- [ ] Dashboard → Settings → Conectar Twitch

## Fase 4 — Seguridad
- [ ] AbuseIPDB + IPQualityScore keys
- [ ] MFA activado (admin) en Settings
- [ ] `/docs` → 404 en producción
- [ ] `/health` → 200

Ver guía detallada: [DEPLOYMENT_FREE.md](./DEPLOYMENT_FREE.md)
