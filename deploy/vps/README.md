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

## Despliegue automatico desde Windows (recomendado)

1. Crea el VPS (Hetzner CX22, Ubuntu 24.04) y el DNS **A** `api` → IP del VPS ([guia DNS](DNS.md)).
2. Opcional: copia `config.example.ps1` → `config.ps1` con IP y dominio.
3. Ejecuta:

```powershell
cd deploy
.\deploy-vps.ps1
```

Te pedira IP, dominio (`api.tudominio.com`), subira `.env`, clonara el repo, instalara Docker y copiara las variables de Vercel al portapapeles.

Con config guardada:

```powershell
.\deploy-vps.ps1 -VpsIp "95.217.x.x" -ApiDomain "api.midominio.com"
```

## Manual (paso a paso)

### Generar `.env`

```powershell
cd deploy\vps
.\prepare-vps-env.ps1
```

### Subir al VPS

```powershell
scp deploy\vps\.env root@TU_IP:~/Anti-Bots/deploy/vps/.env
ssh root@TU_IP "cd Anti-Bots && git pull && bash deploy/vps/setup-server.sh"
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
