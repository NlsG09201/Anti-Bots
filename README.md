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

Desde la raíz, los comandos de npm evitan cambiar de carpeta para las tareas habituales. Instale primero las dependencias del frontend con `npm ci --prefix frontend`. Para el backend, cree el entorno que usa VS Code y Pylance e instale sus dependencias:

```bash
uv venv backend/.venv --python 3.11
uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements.txt -r backend/requirements-dev.txt
```

En Linux/macOS, sustituya `backend/.venv/Scripts/python.exe` por `backend/.venv/bin/python`.

```bash
npm run dev            # Frontend
npm run lint           # ESLint del frontend
npm run typecheck      # TypeScript del frontend
npm run build          # Build del frontend
npm run test:backend   # Suite backend
npm run stack:up       # PostgreSQL, Redis, API y worker locales
npm run stack:down     # Detener el stack sin borrar sus datos
```

Para Spring, ejecute `mvn --batch-mode verify` desde `backend-spring/`. El build de Vercel instala el frontend con `npm ci`, usando su lockfile.

Los pasos de CI están en `.github/workflows/ci.yml`; el análisis estático multilenguaje usa `.github/workflows/codeql.yml`, y el análisis de dependencias OSV corre en PR/merge queue y semanalmente en `.github/workflows/dependency-scan.yml`. Ambos publican resultados en GitHub Code Scanning cuando está habilitado en el repositorio. La API expone `/health`; este endpoint comprueba que el proceso responde, no certifica por sí solo la disponibilidad de PostgreSQL, Redis ni proveedores externos.

Para levantar el stack local con PostgreSQL, Redis, API y worker (sin cargar variables de Render):

```bash
npm run stack:up
```

La API queda en `http://localhost:8000`; `/health` es liveness y `/readyz` comprueba PostgreSQL y Redis TCP. Las credenciales del Compose son exclusivamente locales y deben reemplazarse antes de compartir o exponer esos servicios.

## Despliegue

- Render: consulte `render.yaml` y `docs/OPENAI_SETUP.md`; los secretos se configuran en el panel de Render o en el flujo de importación protegido.
- VPS: siga [`deploy/vps/README.md`](deploy/vps/README.md).
- Integraciones de plataforma: [`docs/KICK_WEBHOOKS.md`](docs/KICK_WEBHOOKS.md) y [`docs/PLATFORM_INTEGRATION_AUDIT.md`](docs/PLATFORM_INTEGRATION_AUDIT.md).
- Esquema PostgreSQL y límites actuales de Alembic: [`docs/DATABASE_MIGRATIONS.md`](docs/DATABASE_MIGRATIONS.md).
- Backup PostgreSQL y restauración aislada: [`docs/DATABASE_BACKUP_RECOVERY.md`](docs/DATABASE_BACKUP_RECOVERY.md).

Revise [`docs/ENGINEERING_PROGRESS.md`](docs/ENGINEERING_PROGRESS.md) para el estado de arquitectura, prioridades y verificaciones pendientes.
