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
