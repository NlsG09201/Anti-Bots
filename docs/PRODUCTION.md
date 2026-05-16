# Configuración de producción

## Variables críticas

```env
APP_ENV=production
APP_DEBUG=false
COOKIE_SECURE=true
COOKIE_SAMESITE=strict
TRUSTED_HOSTS=api.tudominio.com
APP_CORS_ORIGINS=https://app.tudominio.com
```

Al arrancar con `APP_ENV=production`, la API:
- Rechaza secretos por defecto (`dev-secret-key...`)
- Exige `COOKIE_SECURE=true`
- Oculta `/docs` y `/openapi.json`
- Activa CSRF para requests con cookies
- Activa TrustedHost

## Integraciones activas en código

| Variable | Función |
|----------|---------|
| `ABUSEIPDB_API_KEY` | Reputación IP |
| `IPQUALITYSCORE_API_KEY` | VPN/proxy/TOR/datacenter |
| `VIRUSTOTAL_API_KEY` | Análisis multi-engine de IP |
| `CLOUDFLARE_API_TOKEN` + `ZONE_ID` | Bloqueo IP en edge |
| `CLOUDFLARE_AUTO_BLOCK=true` | Auto-bloqueo si risk >= threshold |
| `MAXMIND` + `GEOIP_DATABASE_PATH` | Geo local (descargar GeoLite2) |
| `TWITCH_*` | OAuth + EventSub webhooks |
| `DISCORD_WEBHOOK_URL` | Alertas |

## Descargar GeoLite2 (opcional)

```bash
# Con MAXMIND_LICENSE_KEY en .env
./scripts/download-geoip.sh
```

Coloca el `.mmdb` en `backend/data/GeoLite2-City.mmdb`.

## Autenticación segura

- **Access token**: solo en memoria del navegador (15 min)
- **Refresh token**: cookie `HttpOnly` + `Secure` + `SameSite`
- **CSRF**: cookie `ss_csrf_token` + header `X-CSRF-Token`
- **Logout**: revoca refresh en BD + blacklist Redis

## Endpoints de auth

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/api/v1/auth/csrf` | Obtener token CSRF (frontend) |
| POST | `/api/v1/auth/login` | Login (setea cookies) |
| POST | `/api/v1/auth/refresh` | Renovar access (usa cookie) |
| POST | `/api/v1/auth/logout` | Cerrar sesión |
