# Despliegue alternativo en Koyeb

Koyeb puede ejecutar el backend FastAPI desde el Dockerfile existente. El repositorio es público, así que se puede iniciar el asistente de despliegue directamente desde aquí:

[![Desplegar API en Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&builder=dockerfile&repository=github.com%2FNlsG09201%2FAnti-Bots&branch=main&workdir=backend&dockerfile=Dockerfile&name=streamshield-api&instance_type=free&regions=was&ports=8000%3Bhttp%3B%2F)

## Configuración del servicio

El botón selecciona el repositorio `NlsG09201/Anti-Bots`, la rama `main`, el Dockerfile de `backend`, el puerto `8000`, la región `was` (Washington, D. C.) y la instancia gratuita. En la revisión del servicio, confirma el chequeo HTTP `GET /health`.

Configura estas variables en el panel de Koyeb:

### Secretas

- `DATABASE_URL`: conexión PostgreSQL `postgresql+asyncpg://...`. Se puede conservar Neon; si Neon sigue suspendido por cuota, las rutas de datos responderán `503` hasta que la base vuelva a aceptar conexiones.
- `APP_SECRET_KEY`: clave aleatoria de al menos 32 caracteres.
- `JWT_SECRET_KEY`: clave aleatoria de al menos 32 caracteres.
- `AES_ENCRYPTION_KEY`: clave aleatoria de exactamente 32 bytes.

No pegues claves privadas en GitHub ni en este archivo.

### Configuración

```text
APP_ENV=production
APP_DEBUG=false
PORT=8000
COOKIE_SECURE=true
COOKIE_SAMESITE=none
APP_CORS_ORIGINS=https://anti-bots.vercel.app,https://anti-bots-vhbo.vercel.app
APP_FRONTEND_URL=https://anti-bots.vercel.app
TRUSTED_HOSTS=*.koyeb.app
PLATFORM_MONITOR_ENABLED=false
PLATFORM_MONITOR_RUN_IN_API=false
PLATFORM_HEALTH_ENABLED=false
LIVE_INTEL_ENABLED=false
VIEWER_FLOW_ENABLED=false
BACKGROUND_CHANNEL_MONITOR_ENABLED=false
EVENT_PIPELINE_ENABLED=false
EVENT_QUEUE_ENABLED=false
EVENT_QUEUE_WORKER_IN_API=false
EVENT_REALTIME_PUBSUB_ENABLED=false
TWITCH_INSIGHTS_ENABLED=false
WEKA_J48_ENABLED=true
WEKA_PYTHON_ENABLED=true
WEKA_JVM_EAGER_START=false
WEKA_JVM_MAX_HEAP=128m
```

Los monitores periódicos y las funciones de eventos que exigen Redis quedan desactivados en este perfil gratuito. El API, el análisis Weka y Power BI bajo demanda permanecen habilitados.

## Conectar el frontend de Vercel

Cuando Koyeb asigne el dominio HTTPS, configura estas variables de entorno en Vercel con ese dominio (sin `/` final):

```text
API_PROXY_TARGET=https://<dominio-koyeb>
NEXT_PUBLIC_API_URL=https://<dominio-koyeb>
NEXT_PUBLIC_API_DIRECT_URL=https://<dominio-koyeb>
NEXT_PUBLIC_WS_URL=wss://<dominio-koyeb>
```

Luego reconstruye el frontend en Vercel. Los endpoints OAuth de Twitch y Kick también deben actualizarse en sus respectivos paneles con el dominio Koyeb.

## Límites del plan gratuito

Koyeb ofrece una sola instancia web gratuita por organización, con 512 MB de RAM y 0,1 vCPU; escala a cero tras una hora sin tráfico. Es útil para pruebas y tráfico ligero, no es una instancia siempre activa. La base PostgreSQL gratuita de Koyeb tiene un límite de cinco horas de cómputo al mes, por eso esta guía conserva PostgreSQL externo en vez de usar esa base como reemplazo de Neon.

Cambiar el host del API no desbloquea una cuota agotada en Neon. Para que login, analítica y operaciones con datos funcionen, Neon debe reanudar el acceso o hay que migrar la base completa a otro PostgreSQL antes de cambiar `DATABASE_URL`.
