# Anti-Bots AI

Plataforma de ciberseguridad para moderación y análisis de actividad en directos. El repositorio combina una API FastAPI, un servicio Spring, un frontend Next.js, trabajadores asíncronos e infraestructura de datos/observabilidad.

## Arquitectura actual

- `backend/`: API FastAPI, reglas de seguridad, integraciones Twitch/Kick/YouTube, análisis OpenAI, persistencia PostgreSQL y tareas.
- `backend-spring/`: servicio Java 21 independiente, compilado y verificado en CI.
- `frontend/`: aplicación Next.js.
- `deploy/`: despliegues Render/VPS, contenedores y configuraciones locales.
- `infrastructure/`: infraestructura y observabilidad.
- `business-intelligence/`: modelos, SQL y artefactos de analítica.
- `docs/`: decisiones y guías operativas.

Los eventos de Kick se verifican y persisten antes de procesarse; Redis/arq proporciona cola y distribución cuando hay Redis TCP. Upstash REST sirve para comandos de caché, pero no reemplaza Redis TCP para arq, Redis Streams ni pub/sub. Twitch conserva su integración independiente.

## Desarrollo y verificación

Requisitos: Python 3.11 para el backend, Java 21 para Spring, Node.js 20 para el frontend, PostgreSQL y (para las funciones de cola en tiempo real) Redis TCP. Configure las variables desde `.env.example` en un archivo local ignorado por Git; reemplace todas las claves de ejemplo y no comparta archivos de entorno.

```bash
# Backend (desde backend/)
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q

# Spring (desde backend-spring/)
mvn --batch-mode verify

# Frontend (desde frontend/)
npm ci
npm run build
```

Los pasos completos de CI están en `.github/workflows/ci.yml`. La API expone `/health`; este endpoint comprueba que el proceso responde, no certifica por sí solo la disponibilidad de PostgreSQL, Redis ni proveedores externos.

Para levantar el stack local con PostgreSQL, Redis, API y worker (sin cargar variables de Render):

```bash
docker compose -f deploy/local/docker-compose.dev.yml up --build
```

La API queda en `http://localhost:8000`; `/health` es liveness y `/readyz` comprueba PostgreSQL y Redis TCP. Las credenciales del Compose son exclusivamente locales y deben reemplazarse antes de compartir o exponer esos servicios.

## Despliegue

- Render: consulte `render.yaml` y `docs/OPENAI_SETUP.md`; los secretos se configuran en el panel de Render o en el flujo de importación protegido.
- VPS: siga [`deploy/vps/README.md`](deploy/vps/README.md).
- Integraciones de plataforma: [`docs/KICK_WEBHOOKS.md`](docs/KICK_WEBHOOKS.md) y [`docs/PLATFORM_INTEGRATION_AUDIT.md`](docs/PLATFORM_INTEGRATION_AUDIT.md).

Revise [`docs/ENGINEERING_PROGRESS.md`](docs/ENGINEERING_PROGRESS.md) para el estado de arquitectura, prioridades y verificaciones pendientes.
