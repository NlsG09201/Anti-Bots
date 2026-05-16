# DNS para la API en VPS

Tu API debe resolverse a la **IP publica del VPS** antes de que Caddy obtenga el certificado HTTPS.

## Registro necesario

| Tipo | Nombre | Valor | TTL |
|------|--------|-------|-----|
| **A** | `api` | `IP_DEL_VPS` | 300 (o Auto) |

Resultado: `api.tudominio.com` → IP del VPS.

Si usas el dominio raiz (`tudominio.com` sin subdominio), el nombre es `@` en lugar de `api`.

## Cloudflare

1. DNS → **Add record**
2. Type **A**, Name **api**, IPv4 **IP del VPS**
3. Proxy: **DNS only** (nube gris) la primera vez, para evitar problemas con Let's Encrypt
4. Tras confirmar `/health`, puedes activar proxy naranja si quieres CDN/WAF

## Hetzner DNS

1. [dns.hetzner.com](https://dns.hetzner.com) → tu zona
2. **Add record** → Type A, Name `api`, Value IP del servidor
3. En el VPS de Hetzner, la IP aparece en el panel del servidor (IPv4)

## Namecheap / GoDaddy

Advanced DNS → A Record → Host `api` → Value IP del VPS.

## Comprobar propagacion

```powershell
nslookup api.tudominio.com
# Debe mostrar la IP del VPS
```

En el VPS (tras deploy):

```bash
curl -s https://api.tudominio.com/health
```

## Hetzner: crear el VPS (resumen)

1. [console.hetzner.cloud](https://console.hetzner.cloud) → **Add Server**
2. Ubuntu 24.04, tipo **CX22**, ubicacion cercana a Neon (ej. Ashburn / N. Virginia)
3. SSH key recomendada (pega tu clave publica)
4. Crear → copiar **IPv4**
5. DNS A `api` → esa IP
6. En Windows: `deploy\vps\vps-deploy.ps1`
