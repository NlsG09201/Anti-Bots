# Resumen — Manifiestos Kubernetes Anti-Bots

## Artefactos generados
- `infrastructure/kubernetes/manifests/workloads.yaml`: namespace `streamshield`, tres ConfigMaps, cuatro Deployments y tres Services ClusterIP (API, Spring Boot y frontend). El worker no tiene puerto ni Service.
- `.github/modernize/deployment/plan.md` y `.github/modernize/deployment/progress.md`: seguimiento del trabajo.

## Configuración relevante
- Imágenes apuntan a `registry.example.com/<imagen>:replace-me`; se referencia el Secret de pull externo `registry-pull-secret` (eliminar si el registry es público).
- Los valores secretos no se crean ni se escriben en el repositorio. Los Pods usan `secretKeyRef` contra el Secret preexistente `streamshield-secrets`, con keys identificadas en el manifiesto.
- PostgreSQL, Redis y MongoDB permanecen externos/gestionados.
- Probes: API `/health:8000`, Spring `/health:8080`, frontend TCP/3000 y worker mediante comprobación del proceso PID 1.
- Next.js standalone debe construirse con `API_PROXY_TARGET=http://streamshield-api:8000`; su rewrite queda fijada durante el build. Cambiar dominios `example.com`, registry, tags y valores/keys externos antes de desplegar.

## Validación
- `js-yaml` parseó correctamente los 11 documentos YAML; comprobaciones estáticas de recursos, probes, selectores, Services, ConfigMap refs y ausencia de Service para el worker completadas.
- VS Code no reportó errores para el manifiesto.
- `kubectl` client 1.34.1 está disponible, pero su dry-run no pudo validar con el API server porque no hay clúster local escuchando en `localhost:8080`.
- No se construyeron imágenes, iniciaron contenedores ni aplicaron recursos.

## Incidencias
La verificación de esquema del API server queda pendiente hasta disponer de un clúster/contexto Kubernetes. No se detectaron errores de sintaxis YAML.
