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
- `compileall` terminó correctamente con el Python 3.14 disponible; no equivale a probar el runtime 3.11.
- No se pudo ejecutar pytest porque pytest no está instalado en el intérprete disponible. Docker Compose tampoco se pudo validar: el ejecutable local no pudo leer su configuración de usuario y no expuso el subcomando `compose`.
- No se ejecutó despliegue ni se verificó el estado en Render, Vercel, Neon o Upstash.
