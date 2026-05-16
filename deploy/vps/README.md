# StreamShield en VPS (Docker + Caddy)

Arquitectura:

```
Vercel (frontend) → https://api.tudominio.com → Caddy → API (uvicorn) → Neon PostgreSQL
```

## Requisitos

- VPS Ubuntu 22.04+ (Hetzner CX22, DigitalOcean Droplet, etc.)
- Dominio con registro **A** (o **AAAA**) apuntando a la IP del VPS
- Base Neon ya creada (`Anti-Bot`)
- Repo clonado en el servidor

## 1. Generar `.env` en Windows

```powershell
cd deploy\vps
.\prepare-vps-env.ps1
# Dominio: api.tudominio.com
```

O manualmente: `cp env.example .env` y edita en el VPS.

## 2. Subir al VPS

```powershell
# Ejemplo (cambia user e IP)
scp deploy\vps\.env root@TU_IP:~/Anti-Bots/deploy/vps/.env
```

En el VPS:

```bash
git clone https://github.com/NlsG09201/Anti-Bots.git
cd Anti-Bots
# Coloca .env en deploy/vps/.env
bash deploy/vps/setup-server.sh
```

## 3. Neon

Si Neon tiene **IP allowlist**, añade la IP pública del VPS (Neon Console → Settings).

## 4. Vercel

| Variable | Valor |
|----------|--------|
| `API_PROXY_TARGET` | `https://api.tudominio.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://api.tudominio.com` |

Redeploy del frontend.

## 5. Twitch

Actualiza en Twitch Developer Console:

- OAuth Redirect: `https://api.tudominio.com/api/v1/integrations/twitch/callback`
- EventSub: `https://api.tudominio.com/api/v1/webhooks/twitch`

## Comandos útiles

```bash
cd ~/Anti-Bots/deploy/vps
docker compose logs -f api
docker compose ps
docker compose up -d --build   # tras git pull
curl -s https://api.tudominio.com/health
```

## Redis opcional

```bash
docker compose --profile redis up -d
# En .env: REDIS_URL=redis://redis:6379/0
```

## Coste orientativo

| Proveedor | Plan | ~USD/mes |
|-----------|------|----------|
| Hetzner CX22 | 2 vCPU, 4 GB | ~4–5 |
| DigitalOcean | Basic 1 GB | ~6 |
| Vultr | 1 vCPU 1 GB | ~6 |

Sin cold start ni límites agresivos del free tier de Render.
