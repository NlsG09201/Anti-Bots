# Esquema y migraciones PostgreSQL

## Estado actual

- FastAPI crea tablas ausentes con `Base.metadata.create_all()` durante el arranque. Esto no altera columnas ni índices de tablas que ya existen.
- `run_startup_migrations()` aplica SQL directo para el enum `platform` y una actualización de settings de Kick. No usa Alembic.
- Alembic contiene `002_add_alerts_table`, `003_kick_webhook_events` y `004_ai_usage_records`. La revisión 002 declara `down_revision = None` aunque su docstring referencia una revisión `001_initial_schema` que no está en el repositorio. Las revisiones 003 y 004 requieren tablas base como `streams` y `tenants`.
- La revisión 002 describe un modelo `alerts` antiguo (`dismissed`, `alert_type`, `description`, entre otros). El modelo SQLAlchemy operativo `app.infrastructure.database.models.Alert` usa `status`, `message` y `attack_id`. No deben aplicarse ambas definiciones al mismo esquema.
- Por estas diferencias, la cadena Alembic actual no es una ruta verificada de instalación nueva ni de actualización de una base existente. No ejecutar `alembic upgrade` o `downgrade` en producción hasta reconciliar y probar el baseline.

## Procedimiento seguro para cambios de esquema

1. En una copia aislada, guardar un backup PostgreSQL y verificar su manifiesto con `python -m scripts.database_backup verify <archivo>`; consultar el [procedimiento de backup y recuperación](DATABASE_BACKUP_RECOVERY.md).
2. Capturar el esquema existente sin datos sensibles: `pg_dump --schema-only` y `alembic current`/`alembic history`.
3. Comparar ese esquema con `Base.metadata` y resolver explícitamente los modelos duplicados/obsoletos antes de crear un baseline inmutable.
4. Escribir revisiones forward-only y aditivas cuando sea posible. Para cambios de datos, definir lotes, idempotencia y una consulta de verificación posterior.
5. Probar `upgrade` sobre una base vacía y sobre una copia restaurada de la base existente; comparar tablas, columnas, índices y conteos antes/después.
6. Antes de producción, conservar backup probado y usar una ventana de despliegue. El rollback operativo es restaurar el backup o desplegar código compatible; no ejecutar un `downgrade` que borre tablas con datos.

## Contrato futuro

- La aplicación no debe ejecutar DDL de evolución en cada arranque.
- El esquema debe cambiar mediante migraciones versionadas en el mismo release que el código compatible.
- CI debe probar la migración desde cero y la actualización desde un esquema anterior soportado.
- Los índices operativos documentados en `backend/sql/enterprise_indexes.sql` deben pasar a revisiones versionadas antes de considerarse garantizados en todos los entornos.

Hasta completar la reconciliación, `create_all` solo garantiza crear tablas faltantes; no es una migración para cambios de esquema existentes.
