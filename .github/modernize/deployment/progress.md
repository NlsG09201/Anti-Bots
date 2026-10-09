# Progreso de despliegue — Anti-Bots Kubernetes

- Análisis del repositorio: completado (backend FastAPI detectado; Dockerfiles y manifiesto Kubernetes existente inspeccionados).
- Generación del plan: completada.
- Control de versiones: completado; rama previa `appmod/java-upgrade-20261009215725`, rama actual `modernize/python-20261009222000`.
- Artefactos de despliegue: completados en `infrastructure/kubernetes/manifests/workloads.yaml`.
- Verificación: YAML parseado con js-yaml; comprobados 11 recursos, 4 Deployments, probes, referencias a ConfigMap/registry, selectores/Services y aislamiento del worker. `kubectl` client está instalado, pero su dry-run intentó contactar un API server local no disponible; no se aplicó ningún recurso.
- Resumen: completado en `.github/modernize/deployment/summary.md`.

## Alcance acordado
Manifiestos Kubernetes para FastAPI, worker dedicado, backend Spring Boot Java 25 y frontend Next.js standalone. PostgreSQL, Redis y MongoDB externos/gestionados. Sin Compose, sin secretos en claro y sin iniciar contenedores.
