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

- `enqueue_event_job` treats arq's `None` response as accepted only when the deterministic job is active or its retained result succeeded. A retained failure or missing job state falls back to inline processing; a processing exception leaves the Redis Stream entry pending for reclaim.
- The Redis pool is closed in a `finally` block, and close errors are logged without converting an accepted enqueue into an inline fallback.
- Added tests for active duplicates, successful and failed retained results, missing job state, inline recovery, and close failures after enqueue.
- arq's enqueue implementation can return `None` for a retained result, not only an active queued job. This distinction is necessary to avoid acknowledging a stream entry whose previous arq attempt exhausted its retries.
- Verification after the correction: full backend suite passed (`135 passed, 1 skipped, 20 warnings`). Warnings are the existing sklearn artifact-version and framework deprecations.

## arq queue depth observability (2026-10-30)

- Queue status now reads the actual arq sorted-set depth with `ZCARD`, reports every event category on the shared queue, and reflects the queue feature flag accurately.
- Queue-stat failures report only the exception type; the Redis pool is closed on all paths.
- Added tests for real-depth reporting, shared category labels, disabled state, safe failure reporting, and pool cleanup.
- Verification: full backend suite passed (`128 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## arq retry exhaustion dead-lettering (2026-10-30)

- The event worker now uses a configurable `EVENT_QUEUE_MAX_TRIES` limit (default 5, constrained to 1–20). When a stream-backed pipeline job fails on its final attempt, it persists the event and error type to the existing dead-letter stream before acknowledging the already-enqueued source entry.
- Intermediate failures continue to raise to arq for retry. Added tests verify intermediate attempts do not ack and terminal failures write the dead letter before acking.
- Verification: focused event-delivery tests passed (`13 passed`); full backend suite passed (`137 passed, 1 skipped, 20 warnings`). Existing sklearn artifact-version and framework deprecation warnings remain.

## Prometheus event-pipeline gauges (2026-10-30)

- Added bounded-cardinality gauges for arq queue depth/availability, Redis Stream length/pending/consumer count, and dead-letter length/availability.
- A tracked API-lifespan task refreshes those gauges at the configured `EVENT_METRICS_REFRESH_SECONDS` interval, independent of authenticated status endpoint traffic; task cancellation follows the existing lifespan registry.
- Added tests for metric refresh and unavailable-source markers.
- Verification: full backend suite passed (`130 passed, 1 skipped, 20 warnings`); Python compile check and `git diff --check` passed. Existing sklearn artifact-version and framework deprecation warnings remain.

## Prometheus alert rules (2026-10-30)

- Added alert rules for API and exporter availability, HTTP 5xx ratio and p95 latency, enabled queue/stream availability, event backlogs, missing stream consumers, and dead-letter contents. Alert rules use availability and feature-enabled gauges so intentionally disabled components do not fire outage alerts.
- The enterprise Compose stack mounts the full Prometheus configuration directory. CI runs `promtool check config` against the config and alert files.
- Updated the deployment guide with alert locations and the current operational limit: no Alertmanager receiver is configured, so alerts are visible in Prometheus but are not sent to an external notification channel.
- Verification: full backend suite passed (`137 passed, 1 skipped, 20 warnings`); `git diff --check` passed. Prometheus rule parsing awaits the new CI check because Docker Desktop is unavailable in this environment.

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

## Vercel skew protection and Render deploy safeguards (2026-10-30)

- The frontend now passes Vercel's `VERCEL_DEPLOYMENT_ID` to Next.js so navigations and static assets can detect stale clients across deployments. The Vercel deployment guide now requires automatic system environment exposure for this setting.
- The GitHub Render workflow now passes the environment-file secret via a process environment variable instead of interpolating it into shell source, and pins the service name to `anti-bots-api`.
- The Render push script now defaults to the Blueprint's actual API service name, rejects known production startup blockers before any Render API request, and omits API error bodies and malformed API-key prefixes from logs. The Twitch setup helper uses the same service name.
- Added five offline tests for valid production config, loopback hosts, missing/invalid native Redis, and the explicit all-dependent-features-disabled fallback. Added a CI job for these deployment-tool checks.
- Verification: all five deployment-tool tests passed. Frontend production build passed after the deployment-ID change. The Render environment still needs a real native `REDIS_URL` and corrected dashboard `TRUSTED_HOSTS`; neither this workspace nor CI was used to change or deploy live services.

## Stream persistence boundary and backup tamper coverage (2026-10-30)

- Added `StreamRepository` for tenant-scoped get/list and platform/channel lookup operations. Stream API routes now delegate those queries to the repository; detail access continues returning 404 for another tenant's stream.
- Added API tests for own-tenant detail access, cross-tenant detail hiding, and tenant-only stream listing.
- The backend suite exposed an existing backup test fixture that replaced a dump with different bytes of the same length while expecting the size-mismatch error. Changed that fixture to different-length data and added a separate equal-length tamper test that verifies checksum rejection.
- Verification: full backend suite passed (`147 passed, 1 skipped, 22 warnings`). Remaining warnings include scikit-learn model artifact version mismatches and FastAPI/Starlette deprecations. No database or live service was changed.

## Stream watch use-case extraction (2026-10-30)

- Moved Twitch, Kick, YouTube, and TikTok watch-channel lookup/persistence and Kick subscription reconciliation from the API module into `StreamWatchService`; the route now validates transport input, maps known errors, and serializes the response.
- Unexpected provider errors are logged by type and return a generic client message instead of echoing exception text that may include provider response data.
- Added an authenticated YouTube watch-route test that verifies monitor settings and response compatibility without calling the live provider.
- Verification: full backend suite passed (`148 passed, 1 skipped, 23 warnings`). The same sklearn artifact and FastAPI/Starlette deprecations remain.

## Static security analysis workflow (2026-10-30)

- Added a scheduled and push/PR CodeQL workflow for GitHub Actions, Python, Java/Kotlin, and JavaScript/TypeScript. The Java analysis builds the existing Spring Maven module; interpreted languages use no-build mode.
- Scoped workflow permissions to repository read access plus the code-scanning upload permission. README now points to the workflow and notes that GitHub Code Scanning must be enabled for results to publish.
- Workflow uses CodeQL Action v4 and the documented language-specific build modes. Remote GitHub execution is not available in this workspace; the first workflow run must confirm repository settings and autobuild compatibility.

## Database migration safety audit (2026-10-30)

- Confirmed API and worker startup call `Base.metadata.create_all()` followed by two inline PostgreSQL updates; Alembic is not part of runtime startup.
- Alembic currently has no `001_initial_schema` revision although 002 references it in its docstring, 003/004 require pre-existing core tables, and 002's legacy `alerts` schema conflicts with the active SQLAlchemy `Alert` model. An empty-database Alembic upgrade and an existing-production adoption are therefore not verified.
- Added `docs/DATABASE_MIGRATIONS.md` with the observed behavior, safe baseline/adoption steps, backup/restore rollback, and future CI contract. Linked it from README.
- No migration was applied or rewritten: the actual deployed schema and revision state could not be inspected from this workspace, and changing the baseline without that evidence risks data loss or startup failure.
- Removed the unregistered legacy alert router, enhanced persistence engine, repository, and duplicate domain model after confirming no active imports; the authenticated tenant-scoped alert endpoints and current ORM model remain in place. Replaced `DATABASE_ALERTS_IMPLEMENTATION.md` with current API/schema guidance.
- `scripts/deploy.sh` now aborts when Alembic upgrade fails instead of suppressing the failure and starting services. Updated the data-store guide to stop implying that the manual enterprise index script is automatically applied.
- Verification after removing the unreachable alert subsystem: backend suite passed (`148 passed, 1 skipped, 23 warnings`).

## Frontend lint cleanup (2026-10-30)

- Removed unused imports, variables, and chart props from dashboard components and cleaned unused error bindings from the public browser scripts.
- Stabilized the SOC threat-series fallback so its `useMemo` dependency does not become a new empty array on every render.
- Kept the full-page navigation for Twitch OAuth because that API endpoint starts an external authorization flow; documented the targeted lint exception at the call site.
- Verification: `frontend/npm run lint` passed with zero warnings and zero errors; the optimized Next.js production build passed and generated all 28 static routes.
- Updated the deployment guide to match the current Render Docker Blueprint and distinguish the API's arq Redis requirement from the optional Celery worker settings; documented the public trusted-host values.

## Dependency vulnerability coverage (2026-10-30)

- CI already audits Python and npm dependencies, while Dependabot updates Python, npm, Maven, and GitHub Actions. Added OSV-Scanner's official reusable workflows for PR/merge-queue delta checks and full scheduled/push scans, covering the unscanned Maven and transitive dependency trees.
- The workflow uses read-only repository permissions plus the code-scanning upload permission required by the upstream workflows. GitHub Code Scanning must be enabled for uploaded findings to appear there.
- The first GitHub workflow run remains the authoritative vulnerability result; it was not executable from this local workspace.

## Sensitive outbound-error logging (2026-10-30)

- Alert webhook and Discord failure logs no longer include webhook URLs or raw HTTP exception messages, which can contain the URL's embedded bearer token. Database connection retry logs now record only the exception type rather than the driver message.
- Wired the documented `ALERT_WEBHOOK_URLS` environment value into centralized settings as a comma-separated list; the alert engine previously referenced a setting that did not exist, so configured custom webhook notifications could fail before sending.
- Added regression tests asserting alert, Discord, and database connection failure logs omit injected secret strings.
- Verification: full backend suite passed (`151 passed, 1 skipped, 23 warnings`). Existing scikit-learn artifact-version and FastAPI/Starlette deprecation warnings remain.

## Twitch EventSub replay-window idempotency (2026-10-30)

- Increased the in-progress Redis idempotency claim to outlive Twitch's entire accepted timestamp window, including future-clock tolerance and a safety margin. Previously the 30-second claim expired while a signed message could still pass the 10-minute timestamp check, allowing a replay to be processed twice.
- Extended the duplicate-delivery regression test to verify the claim TTL covers the accepted replay window. Failed processing still releases the claim so Twitch retries can proceed.
- Verification: full backend suite passed (`151 passed, 1 skipped, 23 warnings`); existing model-artifact and framework deprecation warnings remain.

## Enterprise background worker scheduling (2026-10-30)

- The enterprise Compose stack had a Celery worker but no Celery Beat process, so the configured periodic reputation, cleanup, and correlation tasks were never scheduled. Added a single Beat service using the registered schedule.
- Explicitly separated Redis logical databases for arq (0), Celery broker (1), and Celery results (2) in the API/worker containers, and added restart policies to core data, API, and worker services.
- Enabled Redis AOF persistence on a named volume and switched to `noeviction`; evicting event/queue keys under memory pressure would otherwise silently lose work. Full memory now rejects writes and surfaces backpressure instead of deleting arbitrary queue entries.
- Clarified that Render's API needs `REDIS_URL` for arq regardless of whether the optional Celery worker is deployed; Celery variables do not replace it.
- Added a local-only environment example and changed the Compose instructions to stop copying the production Render import file into the enterprise development stack. Created the ignored local `.env` from that safe example and verified `docker compose ... config --quiet` succeeds; no containers were started.
- Restricted local/enterprise PostgreSQL, Redis, and API host ports to loopback; the previous wildcard bindings exposed unauthenticated developer databases and Redis to every reachable network interface.

## Backup recovery runbook and restore validation (2026-10-30)

- Added an operator runbook for PostgreSQL dump verification, encrypted/off-host storage, explicit empty-target restore, and isolated recovery drills. It states clearly that the utility itself does not schedule, encrypt, or prune backups.
- Added a restore regression test proving archive verification and empty-target checks precede `pg_restore`, and that restore uses a single transaction with stop-on-error without destructive `--clean`/`--create` flags.
- Verification: full backend suite passed (`152 passed, 1 skipped, 23 warnings`); the new restore test uses mocked PostgreSQL tools and no database was touched. Existing scikit-learn artifact-version and FastAPI/Starlette deprecation warnings remain.

## API exception disclosure review (2026-10-30)

- OAuth callbacks for Twitch, Kick, and YouTube now use provider/status-only messages rather than returning provider response bodies or transport exception strings. Power BI and stream-sync errors return stable error codes; Twitch subscription, chat-bot, Weka, WebSocket, and API error logs omit raw exception messages and log exception types.
- Updated other API handlers to avoid `logger.exception` traceback output when it could include request/provider details. The dormant `threat_intelligence_advanced` router was also sanitized; it is not registered by `app.main`.
- Added tests proving OAuth response bodies and request URLs with injected secrets are omitted from user-facing messages, and that Power BI sync returns a generic 503 error.
- Verification: full backend suite passed (`155 passed, 1 skipped, 23 warnings`); `rg` found no raw `str(exc)`/`logger.exception` use remaining under `backend/app/api`. Existing scikit-learn artifact-version and FastAPI/Starlette deprecation warnings remain.

## Consistent API error responses (2026-10-30)

- Added a global 422 validation envelope that reports field locations and error types without echoing submitted values, which may include passwords or tokens.
- Added a global HTTP exception envelope while preserving the existing `detail` field and response headers for client compatibility. Domain exceptions retain their existing envelope.
- Added tests for secret-free validation responses and 404 compatibility.
- Verification: full backend suite passed (`157 passed, 1 skipped, 23 warnings`); `git diff --check` passed. Existing model-artifact and framework deprecation warnings remain.

## Playbook failure disclosure hardening (2026-10-30)

- Playbook action and execution failures now persist stable error codes and log only exception types. Discord notification failures also omit provider exception text; this prevents credentials, request details, or target data from leaking into logs and execution records.
- Added regression tests with injected secret strings covering both action-level partial failure and execution-level failure.
- Verification: focused tests passed (`2 passed`); full backend suite passed (`159 passed, 1 skipped, 23 warnings`); `git diff --check` passed. Existing model-artifact and framework deprecation warnings remain.
- Follow-up tenant-isolation review found alert playbook actions used the incident's `stream_id` as `alerts.tenant_id`, violating the foreign-key contract and risking cross-tenant data corruption. The executor now passes its verified tenant ID to alert creation, with a regression test asserting it differs from the stream ID. Verification after the fix: focused playbook tests passed (`3 passed`); full backend suite passed (`160 passed, 1 skipped, 23 warnings`).

## CI pull request and frontend typecheck coverage (2026-10-30)

- CI, CodeQL, and OSV dependency scans now run for pull requests targeting both `main` and `develop`, matching the branches already used for push workflows. OSV merge-queue checks now cover both branches as well.
- Added an explicit TypeScript typecheck command to frontend CI. It disables incremental output so the check does not modify the repository's tracked `tsbuildinfo` artifact.
- Verification: `npm run typecheck` passed; `git diff --check` passed. Workflow runtime validation remains with GitHub Actions after push.

## Frontend export requests use shared API client (2026-10-30)

- Power BI downloads now go through the centralized API client, so they share bearer-token refresh, 401 handling, and standardized API errors with JSON calls. Added blob response support to the same request path.
- Export failures now render an accessible inline error instead of silently doing nothing. Downloaded filenames and export endpoints are unchanged.
- Verification: `npm run typecheck` and `npm run lint` passed; `git diff --check` passed.

## Playbook mutation authorization (2026-10-30)

- Playbook creation, updates, deletion, and execution now require the stream moderator role or higher; authenticated viewers retain read access but cannot configure or trigger moderation actions.
- Added an API regression test proving viewer access to execution is rejected with 403.
- Verification: authorization test passed; full backend suite passed (`161 passed, 1 skipped, 23 warnings`); `git diff --check` passed. Existing model-artifact and framework deprecation warnings remain.
