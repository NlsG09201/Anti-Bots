#!/usr/bin/env bash
# Ubuntu 22.04/24.04 — instala Docker y levanta StreamShield API
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Anti-Bots}"
VPS_DIR="$REPO_DIR/deploy/vps"

echo "==> StreamShield VPS setup"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Instalando Docker..."
  sudo apt-get update -qq
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME:-$VERSION}") stable" |
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo usermod -aG docker "$USER" || true
  echo "    Reinicia sesión SSH si 'docker' pide sudo."
fi

if [[ ! -f "$VPS_DIR/.env" ]]; then
  echo "ERROR: Falta $VPS_DIR/.env"
  echo "  cp env.example .env && nano .env"
  echo "  O en Windows: deploy\\prepare-vps-env.ps1 y sube .env al VPS"
  exit 1
fi

if ! grep -q '^API_DOMAIN=.\+' "$VPS_DIR/.env"; then
  echo "ERROR: Define API_DOMAIN=api.tudominio.com en .env"
  exit 1
fi

echo "==> Firewall (22, 80, 443)"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow OpenSSH || true
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
  sudo ufw --force enable || true
fi

cd "$VPS_DIR"
echo "==> Build y arranque"
docker compose up -d --build

API_DOMAIN=$(grep -E '^API_DOMAIN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
echo ""
echo "Listo. Comprueba en unos segundos:"
echo "  curl -s https://${API_DOMAIN}/health"
echo ""
echo "Vercel → API_PROXY_TARGET=https://${API_DOMAIN}"
echo "Vercel → NEXT_PUBLIC_WS_URL=wss://${API_DOMAIN}"
