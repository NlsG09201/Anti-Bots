#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/enterprise/docker-compose.enterprise.yml"
ENV_FILE="$ROOT_DIR/deploy/enterprise/.env"

if [ ! -f "$ENV_FILE" ]; then
    cp "$ROOT_DIR/deploy/enterprise/.env.example" "$ENV_FILE"
    echo "Created deploy/enterprise/.env from its example. Configure it, then rerun this script." >&2
    exit 1
fi

docker compose --file "$COMPOSE_FILE" config --quiet

echo "Starting the enterprise stack. The API initializes the database schema on startup."
docker compose --file "$COMPOSE_FILE" up --detach --build --wait

echo "Deployment is healthy."
echo "API:        http://127.0.0.1:8000/health"
echo "Prometheus: http://127.0.0.1:9090"
