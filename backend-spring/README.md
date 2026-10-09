# StreamShield Spring API

Este servicio es el primer módulo real de la migración progresiva de StreamShield a Spring. Se ejecuta como proceso independiente y comparte PostgreSQL, JWT y Redis con el backend FastAPI. No reemplaza ni modifica el servicio que atiende hoy las rutas existentes.

## Capacidades implementadas

- Spring Boot 3.5.16, Spring AI 1.1.8 y Java 21.
- Spring Security Resource Server, validación de tokens JWT HS256 emitidos por StreamShield y autorización por rol.
- Validación de que el usuario siga activo y que el `tenant_id` del token corresponda a su registro.
- Verificación opcional de revocación en la misma clave Redis que usa FastAPI (`ss:blacklist:<jti>`).
- Spring Data JPA para consultar canales del tenant autenticado; Hibernate no crea, altera ni valida el esquema compartido.
- Asistente SOC en `POST /api/v1/assistant/chat`, con el mismo contrato JSON de FastAPI, límites de longitud/historial, Spring AI opcional y respuesta local cuando la IA está deshabilitada o falla.
- Lectura aislada de canales en `GET /api/v1/spring/streams`.
- Comprobación de salud en `/health` y Actuator.
- Imagen de contenedor y verificación Maven en CI.

El agente no aplica sanciones. La IA está desactivada por defecto; activar `AI_ENABLED` requiere configurar `AI_API_KEY` o `OPENAI_API_KEY`. `AI_BASE_URL` y `AI_MODEL` permiten apuntar a un servicio compatible con la API de chat de OpenAI, incluido Groq. El proveedor y el modelo quedan en variables de entorno.

## Configuración de despliegue

Configurar en el servicio Java:

| Variable | Requerida | Descripción |
| --- | --- | --- |
| `SPRING_DATABASE_URL` | Sí | URL JDBC PostgreSQL del mismo servidor/base usada por FastAPI. No reutilizar `DATABASE_URL` si contiene el esquema de SQLAlchemy `postgresql+asyncpg`; Spring necesita `jdbc:postgresql://...`. |
| `SPRING_DATABASE_USERNAME` | Según el proveedor | Usuario PostgreSQL si no está incluido por el mecanismo de conexión del proveedor. |
| `SPRING_DATABASE_PASSWORD` | Sí | Contraseña PostgreSQL. Mantenerla en el almacén de secretos del proveedor. |
| `JWT_SECRET_KEY` | Sí | El mismo secreto de firma HS256 configurado en FastAPI; mínimo 32 bytes UTF-8. No generar un segundo secreto para el módulo. |
| `APP_ENV` | Sí en producción | Usar `production` para que el servicio exija la conexión de revocación Redis al arrancar. |
| `APP_CORS_ORIGINS` | Sí para navegador | Orígenes exactos del frontend, separados por coma. No usar comodín junto con credenciales. |
| `REDIS_URL` | Sí en producción | URL de la misma instancia Redis que usa FastAPI. |
| `SPRING_CHECK_REDIS_BLACKLIST` | Sí en producción | Debe ser `true` para rechazar tokens revocados. En `APP_ENV=production` el servicio no inicia si faltan esta opción o `REDIS_URL`; si Redis deja de responder, las rutas protegidas fallan cerradas con 503. |
| `AI_ENABLED` | No | Por defecto `false`; mantiene disponible la respuesta local sin dependencia de proveedor. |
| `AI_API_KEY` | Solo si se activa IA | Clave del proveedor OpenAI-compatible; puede usarse `OPENAI_API_KEY`. |
| `AI_BASE_URL` | No | Base del proveedor de chat; si no se configura se usa OpenAI. |
| `AI_MODEL` | No | Identificador del modelo habilitado en el proveedor elegido. |
| `PORT` | No | Puerto HTTP; por defecto 8080. |

`SPRING_DATABASE_URL`, `JWT_SECRET_KEY` y la clave de IA nunca deben guardarse en Git. Hibernate está configurado con `ddl-auto: none`: las migraciones y el esquema siguen bajo el control del backend actual.

## Activación progresiva

1. Desplegar este módulo como servicio separado y apuntarlo a PostgreSQL existente con `SPRING_DATABASE_URL` JDBC. No cambiar el servicio FastAPI ni sus rutas en Render.
2. Confirmar `/health`, conectividad PostgreSQL y que el origen del frontend esté autorizado en `APP_CORS_ORIGINS`.
3. Configurar el mismo secreto JWT de FastAPI y la misma instancia Redis; establecer `SPRING_CHECK_REDIS_BLACKLIST=true`. El servicio impide arrancar en producción si falta esta protección.
4. Configurar `NEXT_PUBLIC_SPRING_API_URL` en el frontend únicamente cuando el servicio Java esté disponible. Esa variable dirige el chat del asistente a `/api/v1/assistant/chat` en Spring; si está vacía, el frontend conserva el endpoint FastAPI actual.
5. Mantener FastAPI como responsable del resto de rutas, WebSocket, OAuth, integraciones de plataforma, ingestión, detección, mitigación y analítica hasta migrar cada capacidad con pruebas de contrato y datos.

El enrutamiento del chat es opcional y no se activa por defecto. No se agregó el servicio al blueprint de Render para evitar que un despliegue existente intente iniciar una instancia Java sin secretos JDBC/JWT. La migración completa requiere paridad funcional de las rutas de FastAPI antes de cambiar el origen general del frontend.

## Verificación

El flujo de CI ejecuta `mvn verify` y construye la imagen Docker. Las pruebas cubren la respuesta local del agente, compatibilidad JWT HS256, rechazo de solicitudes anónimas, acceso de analista, restricción de roles e aislamiento entre tenants. El módulo se construye desde `backend-spring/` y su Dockerfile empaqueta la aplicación como una imagen independiente.
