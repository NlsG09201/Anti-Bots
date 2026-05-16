#!/bin/bash
set -euo pipefail

echo "=== StreamShield Deployment ==="

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example - configure before production deploy"
fi

echo "Building containers..."
docker compose build

echo "Starting infrastructure..."
docker compose up -d postgres redis rabbitmq

echo "Waiting for database..."
sleep 10

echo "Running migrations..."
docker compose run --rm api alembic upgrade head || true

echo "Starting application services..."
docker compose up -d api celery-worker celery-beat frontend nginx

echo "Starting monitoring..."
docker compose up -d prometheus grafana loki

echo "=== Deployment Complete ==="
echo "Frontend: http://localhost:3000"
echo "API:      http://localhost:8000/docs"
echo "Grafana:  http://localhost:3001"
