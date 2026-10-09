# Plan de manifiestos Kubernetes — Anti-Bots

## Alcance
Generar YAML Kubernetes de producción para los cuatro workloads solicitados, sin modificar código fuente, provisionar PostgreSQL/Redis/MongoDB, generar Compose ni iniciar contenedores. Los almacenes de datos se consideran externos/gestionados y se consumen mediante configuración del usuario.

## Workloads
1. FastAPI API: `backend/Dockerfile`, imagen parametrizada `REGISTRY_PLACEHOLDER/streamshield-api:TAG_PLACEHOLDER`, puerto 8000, HTTP probes en `/health`.
2. Worker: `backend/Dockerfile.worker`, imagen `REGISTRY_PLACEHOLDER/streamshield-worker:TAG_PLACEHOLDER`, proceso sin puerto ni Service; verificarlo con probes exec compatibles sin introducir nuevas dependencias (usar `python -c` para comprobar el proceso).
3. Spring Boot: `backend-spring/Dockerfile`, Java 25, imagen `REGISTRY_PLACEHOLDER/streamshield-spring:TAG_PLACEHOLDER`, puerto 8080, HTTP probes en `/health`.
4. Next.js standalone: `frontend/Dockerfile`, imagen `REGISTRY_PLACEHOLDER/streamshield-frontend:TAG_PLACEHOLDER`, puerto 3000, probes TCP porque no se ha confirmado un endpoint de salud dedicado.

## Artefactos a crear/modificar
- `infrastructure/kubernetes/manifests/workloads.yaml`: namespace, ConfigMaps no sensibles, Deployments de los cuatro workloads y Services ClusterIP para API, Spring y frontend.
- No crear un objeto Secret: los Deployments referencian `streamshield-secrets` con `secretKeyRef`; el operador debe crearlo/configurarlo de forma segura externamente.
- No modificar el `infrastructure/kubernetes/deployment.yaml` existente.

## Configuración
- Secretos se referencian por `secretKeyRef` desde un Secret preexistente llamado `streamshield-secrets`; valores omitidos deben provisionarse fuera del repositorio. Ejemplos: database/redis/mongodb URLs y secretos de aplicación/integraciones.
- ConfigMap con entorno razonable no secreto para producción y URLs internas de servicios del mismo namespace cuando correspondan.
- Imágenes usan un placeholder de registry/tag y referencian el pull Secret externo `registry-pull-secret`; quitar la referencia si el registry es público. No crear credenciales de registry.
- Para Next.js standalone, construir la imagen con `API_PROXY_TARGET=http://streamshield-api:8000`, ya que las rewrites se fijan durante el build.
- Límites/solicitudes de recursos, usuario no root cuando la imagen lo soporta, probes liveness/readiness/startup, y réplicas moderadas.
- Ningún workload aprovisiona bases de datos.

## Validación
- Revisar YAML y coherencia de selectores, servicios, puertos, nombres de Secret/ConfigMap y probes.
- Ejecutar validación YAML/Kubernetes local si hay herramientas disponibles; si no, hacer comprobaciones estáticas y documentar la limitación.
- No construir imágenes, ejecutar Docker/Compose ni desplegar recursos.
