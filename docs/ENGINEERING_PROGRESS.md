# Estado de ingeniería

Última revisión: 2026-10-29. Este documento registra el estado observado en el repositorio; no implica que los servicios externos estén desplegados o accesibles.

## Inventario verificado

- API FastAPI en Python 3.11, PostgreSQL asíncrono, Redis opcional y trabajadores arq.
- Servicio Spring con Java 21, frontend Next.js, despliegues Render/VPS, infraestructura de observabilidad y carpeta de Business Intelligence.
- CI en GitHub Actions cubre verificación de Spring, importación/pruebas de backend y compilación de frontend.
- Integraciones verificadas en código/documentación: Twitch, Kick, YouTube y OpenAI. TikTok usa capacidades limitadas y está sujeto a restricciones documentadas en `PLATFORM_INTEGRATION_AUDIT.md`.
- La configuración de Redis distingue REST de Upstash (caché) de Redis TCP (colas, Streams y pub/sub).

## Cambios realizados en esta pasada

- Alineado Python de CI a 3.11, la versión del contenedor de backend, para reducir diferencias entre CI y producción.
- Añadido README raíz con mapa de componentes, requisitos, verificaciones y enlaces operativos.
- Añadida esta bitácora con hallazgos y prioridades para continuar por entregas.
- Añadido `/readyz`: prueba PostgreSQL y Redis TCP cuando Redis está configurado; responde con 503 y nombre de dependencia, sin incluir excepciones potencialmente sensibles.
- Añadida prueba de API para readiness y corregido el nombre de la variable AES que CI entrega a los tests (`AES_ENCRYPTION_KEY`).
- Añadido Compose local aislado con PostgreSQL, Redis, API y worker, dependencias con healthchecks y valores locales explícitos; no consume archivos de despliegue.
- CI compila sintácticamente `app`, `scripts` y `tests` antes de ejecutar pytest.
- Configurado Dependabot semanal para dependencias Python, npm, Maven y GitHub Actions.

## Prioridades de trabajo

1. **Salud operativa:** probar readiness con DB/Redis arriba y abajo; definir qué dependencias externas son obligatorias según el perfil de despliegue.
2. **Desarrollo local reproducible:** levantar Compose local; revisar después los Compose existentes que dependen de `deploy/render.import.env`.
3. **CI y calidad:** revisar alertas/PR de Dependabot; asegurar que los tests no dependan de secretos ni proveedores en vivo y ampliar cobertura de migraciones.
4. **Contenedores:** revisar tamaño, reproducibilidad, usuario no-root, dependencias de sistema y caché de builds, preservando Weka/Java y las librerías nativas.
5. **Seguridad y operación:** revisar configuración CORS/proxy, retención de payloads, métricas, alertas y procedimientos de recuperación de workers/webhooks.
6. **Validación de despliegue:** confirmar variables y logs desde Render/VPS con acceso operativo; los valores locales no demuestran el estado desplegado.

## Límites de esta revisión

- No se inspeccionaron ni imprimieron archivos `.env` o secretos.
- No se ejecutó despliegue ni se verificó el estado en Render, Vercel, Neon o Upstash.

## Revisión de seguridad y cambios incrementales (2026-10-29)

### Inventario y hallazgos

- El repositorio mantiene una arquitectura modular existente: FastAPI separa API, servicios, infraestructura, integraciones y workers; Spring y Next.js son aplicaciones independientes. Hay migraciones Alembic, pero también scripts SQL heredados que requieren una revisión de propiedad y orden antes de consolidar el esquema.
- `backend/app/main.py` concentra el registro de rutas, inicialización de dependencias y varios ciclos de trabajo en el proceso API. Ya hay workers dedicados; el siguiente refactor debe definir qué tareas pertenecen al API frente al worker sin cambiar el ciclo de eventos.
- El contenedor del backend instala compiladores y Java en una sola etapa. Ya corre como usuario no root, pero dividir etapas requiere validar las dependencias nativas de Python y Weka.
- CI construye y prueba los tres componentes principales y Dependabot actualiza dependencias. No se observó un job dedicado a escaneo de vulnerabilidades en dependencias ni un flujo de rollback automatizado.
- La validación de arranque de producción comprobaba secretos y base de datos, pero no rechazaba CORS comodín/HTTP ni hosts comodín/loopback; el listado de Render incluía hosts loopback y un sufijo amplio de Render.

### Cambios de esta pasada

- El arranque ahora falla en producción si CORS no contiene orígenes, admite `*`, usa un esquema distinto de HTTPS, o incluye loopback.
- El arranque ahora falla si `TRUSTED_HOSTS` está vacío, admite `*`, o incluye hosts loopback.
- La configuración Render usa los dos nombres de host del servicio en lugar del sufijo general `.onrender.com` y hosts locales. La plantilla VPS ya no recomienda loopback en producción.
- Se añadieron pruebas parametrizadas para configuraciones de producción seguras e inseguras.
- Se corrigió un test previo del asistente que parcheaba `service.settings`, atributo ya eliminado; el test ahora sustituye `get_settings` y deshabilita explícitamente el cliente remoto.

### Verificación y continuidad

- `git diff --check`: pasó sin errores de whitespace.
- El conjunto backend se ejecutó con Python 3.11.15 y las dependencias del proyecto: `95 passed, 1 skipped` en 5.92 s. Quedaron dos deprecations (Starlette/AnyIO y el `event_loop` custom de pytest-asyncio).
- `python -m compileall -q app scripts tests` también pasó con Python 3.11.15.
- Antes de esa ejecución, el conjunto encontró el test del asistente obsoleto; se actualizó el parche de configuración y luego pasó el conjunto completo.
- No se leyeron archivos de entorno/credenciales ni se modificaron datos, bases de datos o servicios desplegados.
- Siguiente: comprobar despliegues Render/VPS con sus dominios reales; ejecutar CI; después separar tareas de ciclo de vida del proceso API de forma incremental y revisar aislamiento tenant en rutas/repositorios.
- En una revisión anterior, `compileall` pasó con Python 3.14; esto no equivale a probar el runtime 3.11. Docker Compose tampoco se pudo validar en esa revisión.

## Remediación de dependencias y verificación ampliada (2026-10-29)

### Cambios

- La auditoría npm encontró 18 advisories, incluido uno crítico en Next.js 14.1.3. Se actualizó Next.js a 16.4.3/React 19.2 y se subieron Lucide React y Recharts dentro de sus versiones compatibles con React 19. El lint usa la configuración flat oficial y ESLint CLI; `next lint` ya no existe en Next 16.
- El frontend usa el transporte WebSocket con reconexión que se cancela al desmontar/cambiar token y cumple el tipo de `useRef` de React 19.
- `pip-audit` encontró advisories en JWT, multipart, cryptography, orjson, scikit-learn, pytest, OpenTelemetry, protobuf, PyMongo y Starlette, además de ECDSA traído por `python-jose`. Se reemplazó `python-jose` por PyJWT con algoritmos explícitos; se actualizaron FastAPI/Starlette, Motor/PyMongo, las versiones vulnerables y el conjunto OpenTelemetry.
- CI ahora limita el token a `contents: read` y ejecuta `npm audit --audit-level=high` y `pip-audit --vulnerability-service osv`.
- La prueba de entrenamiento de modelos ahora inyecta un registry bajo `tmp_path`, para que la suite no sobrescriba los modelos versionados del repositorio.

### Verificación

- Frontend: `npm ci` pasó y encontró 0 vulnerabilidades; `npm audit --audit-level=high` pasó con 0; `npm run build` pasó con Next 16.4.3, compilación TypeScript y las 28 rutas.
- Backend: `pip-audit --vulnerability-service osv -r requirements.txt -r requirements-dev.txt` informó `No known vulnerabilities found`.
- Backend: con Python 3.11.15 y las nuevas dependencias, `python -m pytest tests/ -q --tb=short -x` pasó (`95 passed, 1 skipped`) y `python -m compileall -q app scripts tests` pasó.
- La suite aún emite warnings de compatibilidad al cargar los modelos scikit-learn serializados con 1.4.1.post1 bajo 1.5.0, y deprecations de Starlette/FastAPI. Los artefactos originales se conservaron/restauraron y el test de entrenamiento quedó aislado.
- `npm run lint` se ejecutó y actualmente falla con 18 errores y 31 warnings, en su mayoría reglas React Hooks nuevas sobre sincronización de estado en efectos. No se agregó como gate CI ni se desactivaron esas reglas; el refactor de los componentes queda como siguiente trabajo.
- El estado actual del despliegue Render/VPS no fue verificado.

### Próximos pasos

1. Resolver las reglas de lint de forma estructural y añadir `npm run lint` al CI cuando pase.
2. Migrar/verificar los artefactos scikit-learn conservando predicciones; quitar deprecations de FastAPI/Starlette con cambios compatibles.
3. Separar ciclos de trabajo del proceso FastAPI, revisar aislamiento tenant y contratos Spring/FastAPI, y continuar el runbook operativo/rollback.

## Frontend query polling refactor (2026-10-29)

- Replaced component-local polling effects in the SOC alert, threat timeline, threat map, and suspicious viewer panels with TanStack Query polling. Query keys include stream and tenant identifiers where applicable; polling intervals remain 5, 10, or 15 seconds as before.
- Alert dismissal now invalidates the stream alert query so refreshed data comes through the shared cache. Alert payload metadata is typed as `Record<string, unknown>`.
- The Twitch invite error is derived from the URL during render instead of being copied into state from an effect.
- Assistant moderation mode and Kick bot settings now use query data as defaults and keep edits scoped to the selected stream, without copying query results into state from effects.
- The deployment checklist reads localStorage through `useSyncExternalStore`, with same-tab updates published through a storage event.
- Verification: `npm run build` passed with TypeScript and all 28 routes. `npm run lint` now reports 9 errors and 31 warnings, down from 18 errors; remaining errors are in OAuth callback message state, Twitch moderator/viewer effects, ThemeContext, and one manual memoization rule.
- The current frontend lint errors remain unfixed and lint is not yet a CI gate.

## Frontend state synchronization follow-up (2026-10-29)

- Theme preference now uses a `useSyncExternalStore` subscription to localStorage, matching the deployment checklist's external-store pattern and supporting same-tab and cross-tab updates.
- Viewer-page automatic synchronization is scheduled and cancellable when the selected stream changes; OAuth query refresh no longer overwrites an explicit stream selection.
- Corrected the Power BI threat-series memo dependency so React Compiler can preserve the memo.
- Verification: `npm run build` passed with TypeScript and all 28 routes. `npm run lint` reports 5 errors and 32 warnings. Remaining errors are OAuth feedback state in Channels/Settings/Login and query/form synchronization in Twitch Moderator.

## Frontend lint gate enabled (2026-10-29)

- Removed the remaining effect-driven OAuth feedback updates in Channels, Settings, Login, and Twitch Moderator. Provider status invalidation remains in effects; callback text and YouTube failure details are derived from URL parameters.
- Twitch Moderator configuration now uses server query data as its default and scopes local edits to the active stream. Its OAuth stream parameter initializes the Suspense-wrapped client route.
- Login retains the ability to clear a callback error when a new submission begins.
- Added `npm run lint` to frontend CI after resolving all lint errors.
- Verification: `npm run lint` passed with 0 errors and 32 existing warnings. `npm run build` passed TypeScript and all 28 routes. `git diff --check` passed.

## Backend ban tenant isolation (2026-10-29)

- The active ban creation endpoint accepted a stream UUID without checking its tenant. It now verifies the stream against the authenticated user's tenant before inserting a ban.
- Ban revocation previously loaded a ban by UUID alone. `MitigationService.revoke_ban` now requires a tenant ID and scopes the lookup by both ban and tenant.
- Added API tests proving a user cannot create a ban for another tenant's stream or revoke another tenant's ban.
- Verification: focused tenant-isolation tests passed (2 passed); full backend suite passed (97 passed, 1 skipped, 17 warnings). Existing sklearn model-version and FastAPI/Starlette deprecation warnings remain.

## Authenticated SOC alerts contract (2026-10-29)

- The SOC alert panel was calling unauthenticated endpoints that were not registered by the FastAPI app. It now uses the shared token-aware API client and the active tenant-scoped alert routes.
- The active alert list supports an optional stream filter. It joins through the alert's attack to the stream and checks both alert and stream tenant IDs.
- Added a tenant-scoped dismiss endpoint; cross-tenant alert IDs return not found. Alert rows retain the existing `open`/`dismissed` lifecycle used by the panel.
- Added tests for tenant-filtered alert listing, stream-filtered listing, and cross-tenant dismiss rejection.
- Verification: full backend suite passed (`100 passed, 1 skipped, 19 warnings`); frontend lint passed (`0 errors, 33 warnings`); production build passed TypeScript and all 28 routes.

## Twitch EventSub webhook security (2026-10-29)

- Twitch EventSub callbacks now require a valid HMAC signature before challenge responses or notifications are handled. Message timestamps are limited to a 10-minute replay window with a 30-second future tolerance, and request bodies are capped at 1 MiB.
- Notification IDs are claimed atomically in the cache. Completed duplicates return 204; concurrent/in-progress duplicates request a retry, and failed processing releases its claim for retry. Production rejects notifications when the shared cache is not configured.
- Added coverage for signed callback verification, stale-message rejection, duplicate suppression, retry after processing failure, and atomic in-memory cache claims.
- Verification: full backend suite passed (`107 passed, 1 skipped, 20 warnings`); `python -m compileall -q app scripts tests` and `git diff --check` passed. Existing sklearn artifact-version and FastAPI/Starlette deprecation warnings remain.

## API background task lifecycle (2026-10-29)

- Added a lifespan-owned task registry for background tasks created by the FastAPI process. It retains task references, logs uncaught failures with task name and exception type, and cancels/gathers unfinished tasks during shutdown.
- Twitch Insights loading, the channel monitor, and API-started monitoring/health/viewer-flow engine tasks now use the registry. Existing service-specific stop methods remain responsible for their internal loops.
- Added focused tests for failure logging and shutdown cancellation.
- Verification: full backend suite passed (`109 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version, FastAPI response, and Starlette test-client deprecation warnings remain.

## Event pipeline malformed-entry handling (2026-10-30)

- Redis Stream entries that fail schema/metadata parsing are now written to a bounded `ss:events:dead-letter` stream with source stream, source entry ID, exception type, and original fields. The source entry is acknowledged only after the dead-letter write succeeds, avoiding permanent pending poison messages while retaining a diagnostic copy.
- Invalid JSON metadata and non-object metadata now fail parsing explicitly instead of silently becoming empty metadata.
- Added a Redis-client fake test that verifies dead-letter persistence precedes source acknowledgement.
- Verification: full backend suite passed (`110 passed, 1 skipped, 20 warnings`); `python -m compileall -q app scripts tests` and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Event pipeline pending-entry recovery (2026-10-30)

- The Redis Stream consumer now reclaims idle pending entries with `XAUTOCLAIM` before reading new entries, allowing another consumer to retry work after a process crash or handler failure. Claim idle time is configurable and is never shorter than the arq job timeout plus 30 seconds to reduce duplicate processing while a job is active.
- Reclaimed entries use the same parsing and dead-letter path as new entries.
- Added coverage for reclaiming a stale pending event and the minimum claim idle interval.
- Operational compatibility: `XAUTOCLAIM` requires Redis 6.2 or newer; the local/development Compose definitions use the Redis 7 image family. Verify managed Redis compatibility before enabling this code in older production environments.
- Verification: full backend suite passed (`111 passed, 1 skipped, 20 warnings`); `python -m compileall -q app scripts tests` and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Event pipeline backlog observability (2026-10-30)

- The authenticated pipeline status now reports Redis stream availability, retained length, consumer-group count, actual pending-message count for `ss-processors`, and active consumer count for both main and priority streams.
- Failed `XINFO GROUPS` queries report an unknown pending count and error type instead of presenting a false zero; a stream metadata failure is represented as unavailable.
- Added tests for backlog totals and query-failure reporting.
- Verification: full backend suite passed (`113 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Dead-letter backlog visibility (2026-10-30)

- Pipeline status now includes the dead-letter stream length and configured cap, without returning event payloads. Redis query failures are reported as unavailable with an error type rather than a misleading zero.
- Added coverage for both the dead-letter backlog value and unavailable-query reporting.
- Verification: full backend suite passed (`113 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Event pipeline tenant ownership check (2026-10-30)

- Pipeline processing now verifies that the tenant ID carried by a queued event matches the owner of the referenced stream before invoking ingest logic. Mismatches are logged and rejected without processing.
- Added a regression test proving a cross-tenant event is rejected before the event handler runs.
- Verification: full backend suite passed (`114 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Render startup configuration incident (2026-10-30)

- The supplied Render logs showed a successful image build followed by startup rejection because imported `TRUSTED_HOSTS` contained localhost and 127.0.0.1. Two identical error lines corresponded to the two loopback values.
- Updated ignored local `deploy/render.env` and `deploy/render.import.env` values to the two explicit Render service hosts, added that setting to the tracked import example, and corrected the VPS environment generator to emit only its API host (no loopback or wildcard subdomains). The tracked `render.yaml` already contains the explicit Render hosts.
- Added a production validator test for the explicit Render host pair. Full backend suite passed (`115 passed, 1 skipped, 20 warnings`); `git diff --check` passed.
- The logs also show Redis is not configured. This is a warning rather than the startup blocker; Render environment must include native `REDIS_URL` for Redis Streams, arq queues, and WebSocket pub/sub to operate. No external Render settings were changed or deployment run from this workspace.

## Production Redis dependency validation (2026-10-30)

- Production startup now rejects missing native Redis TCP configuration when the event pipeline, arq queue, or realtime pub/sub is enabled. Upstash REST alone is not accepted for these features. Operators may run without Redis only after explicitly disabling all three features.
- Added coverage for missing Redis, REST-only Redis, and the explicit all-features-disabled fallback.
- Verification: full backend suite passed (`118 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.
- Render still requires a dashboard environment update and redeploy; no live service state was changed.

## Redis URL validation consistency (2026-10-30)

- Startup and Redis client now share one native Redis URL validator, avoiding a false-ready state where a malformed `REDIS_URL` passed startup checks but was rejected by the client.
- Validation checks supported schemes, host, port syntax/range, placeholder credentials, and loopback addresses. Added production tests for malformed ports, HTTP URLs, and IPv4/IPv6 loopback targets.
- Verification: full backend suite passed (`122 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## arq duplicate enqueue handling (2026-10-30)

- `enqueue_event_job` now treats arq's `None` response for an already-existing deterministic job ID as an accepted duplicate. The stream consumer therefore acknowledges the already-queued event instead of processing it inline a second time.
- The Redis pool is closed in a `finally` block, and close errors are logged without converting an accepted enqueue into an inline fallback.
- Added tests for duplicate job IDs and close failures after enqueue.
- Verification: full backend suite passed (`125 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## arq queue depth observability (2026-10-30)

- Queue status now reads the actual arq sorted-set depth with `ZCARD`, reports every event category on the shared queue, and reflects the queue feature flag accurately.
- Queue-stat failures report only the exception type; the Redis pool is closed on all paths.
- Added tests for real-depth reporting, shared category labels, disabled state, safe failure reporting, and pool cleanup.
- Verification: full backend suite passed (`128 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Prometheus event-pipeline gauges (2026-10-30)

- Added bounded-cardinality gauges for arq queue depth/availability, Redis Stream length/pending/consumer count, and dead-letter length/availability.
- A tracked API-lifespan task refreshes those gauges at the configured `EVENT_METRICS_REFRESH_SECONDS` interval, independent of authenticated status endpoint traffic; task cancellation follows the existing lifespan registry.
- Added tests for metric refresh and unavailable-source markers.
- Verification: full backend suite passed (`130 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Enterprise Compose monitoring services (2026-10-30)

- Added Prometheus, PostgreSQL exporter, and Redis exporter to the enterprise Compose stack. Their service names match the existing scrape configuration, and Prometheus data is persisted in a named volume.
- Prometheus UI binds to host loopback only; exporters have no published host ports. The postgres exporter uses the documented datasource URI, username, and password settings.
- `git diff --check` passed. Compose rendering could not be verified because this Docker CLI has no usable Compose subcommand in the sandbox; no containers were started.
- Corrected the API and worker `env_file` paths to load the `deploy/enterprise/.env` file named in the stack's setup instructions, instead of bypassing that local copy and loading `deploy/render.import.env` directly.

## Backend container build and context hardening (2026-10-30)

- Split API and platform-worker Dockerfiles into dependency-build and runtime stages. Compiler and PostgreSQL development packages are confined to build stages; the API runtime retains Java 21 for Weka, while the platform worker retains its existing Java-free runtime.
- Added `backend/.dockerignore` rules for local environment files, SQLite databases, tests, caches, and development dependencies so they are excluded from `COPY . .` image contexts. Tracked AI model artifacts remain included.
- GitHub Actions now builds both backend image variants after the backend checks.
- Local `docker build` could not reach the Docker Desktop Linux engine because its named pipe is absent. `git diff --check` is the local validation; image build verification is delegated to the new CI steps and has not yet run in this session.
