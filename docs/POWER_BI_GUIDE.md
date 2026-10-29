# Guía de Power BI

La guía actual de implementación está en [`business-intelligence/README.md`](../business-intelligence/README.md). Incluye la infraestructura AWS RDS, el Data Warehouse PostgreSQL, ETL idempotente, conexión tenant-scoped, 10 transformaciones M, medidas DAX, publicación y actualización diaria.

El backend expone los endpoints reales documentados en [`project-docs/POWERBI-ANALYTICS.md`](../project-docs/POWERBI-ANALYTICS.md). Las rutas requieren autenticación; no configures una conexión Power BI usando credenciales ficticias ni publiques datos de tenants distintos en un mismo conjunto de credenciales.
