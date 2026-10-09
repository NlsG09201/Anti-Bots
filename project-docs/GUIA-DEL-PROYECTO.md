# Guía sencilla de StreamShield

## ¿Qué es este proyecto?

**StreamShield** es una plataforma de seguridad para canales de transmisiones en vivo. Su objetivo es detectar comportamientos que parecen automatizados o coordinados —por ejemplo, *viewbots*, spam, cuentas que siguen en masa o navegadores automatizados— y mostrarlos rápidamente a la persona que modera el canal.

La aplicación funciona como un pequeño centro de operaciones de seguridad (SOC): recibe señales de un canal, las analiza, calcula un nivel de riesgo y muestra alertas y métricas en tiempo real. Cuando está configurado, también puede registrar o aplicar medidas de mitigación, como cuarentenas, bloqueos y sanciones en Twitch.

## Problema que resuelve

Un ataque de bots puede inflar artificialmente las visualizaciones, ensuciar el chat o afectar una transmisión con muchas cuentas coordinadas. Detectar cada cuenta por separado no suele ser suficiente. StreamShield busca las señales que deja el grupo:

- Muchas entradas en muy poco tiempo.
- Conexiones desde pocas IP, centros de datos, VPN, proxies o TOR.
- Huellas de navegador repetidas o propias de Selenium, Playwright o navegadores sin interfaz.
- Entradas con una cadencia demasiado regular.
- Mensajes repetidos, spam o picos anormales de seguidores.

## Cómo funciona, paso a paso

```text
Canal / widget / webhook de plataforma
              |
              v
        API de StreamShield
              |
              v
 Redis: cola de eventos y tiempo real
              |
              v
 Motor de detección y correlación
    |             |              |
    v             v              v
PostgreSQL   Alertas/acciones   WebSocket
                                  |
                                  v
                         Panel web (SOC)
```

1. **Se recibe un evento.** Puede llegar desde el widget instalado en una página, desde Twitch (EventSub, chat u OAuth) o desde los monitores de plataformas. Un evento puede indicar que alguien entró, escribió en el chat o siguió el canal.
2. **Se pone en la tubería de eventos.** Redis mantiene una cola temporal para que la API no se bloquee ante un pico de actividad. Si la cola está habilitada, un consumidor procesa los eventos de forma asíncrona.
3. **Se evalúa el riesgo.** El backend revisa la huella del navegador, la información de IP/red, el comportamiento reciente del canal y patrones compartidos entre sesiones. También puede consultar fuentes de reputación de IP y directorios de bots conocidos.
4. **Se agrupan las evidencias.** El sistema genera una puntuación de riesgo, un tipo de amenaza y una acción recomendada. Las señales y ataques se guardan en PostgreSQL para poder investigarlos después.
5. **Se avisa al panel.** Las novedades se publican por WebSocket. Por eso el SOC puede actualizar mapas, gráficas, alertas y listas de espectadores sospechosos sin recargar la página.
6. **Se mitiga si procede.** Según el riesgo y la configuración, se pueden registrar bloqueos, cuarentenas, silencios o expulsiones. Para Twitch, algunas acciones pueden enviarse a su API si el canal autorizó los permisos necesarios. La integración con Cloudflare es opcional para bloquear IPs en el perímetro.

> Una alerta no prueba por sí sola que una persona sea un bot. Es una señal de riesgo que conviene revisar antes de tomar medidas permanentes, especialmente si la mitigación automática está activada.

## Qué analiza el sistema

| Área | Ejemplos de señales | Resultado esperado |
| --- | --- | --- |
| Huella del navegador | `webdriver`, navegador sin interfaz, canvas, WebRTC, extensiones, repetición de dispositivo | Riesgo de automatización y de huellas compartidas |
| Red e IP | VPN, proxy, TOR, ASN de centro de datos, reputación y país | Riesgo de red o recomendación de bloqueo |
| Patrón de audiencia | Velocidad de entradas, concentración de IP, cadencia sincronizada | Posible *viewbotting* |
| Chat y seguidores | Mensajes duplicados, alta frecuencia, seguidores recientes en ráfaga | Spam o *followbotting* |
| Anomalías e IA | Comparación con el comportamiento habitual y modelos entrenados | Alerta temprana y puntuación adicional |

## Plataformas

La arquitectura usa adaptadores para no depender de una única plataforma.

- **Twitch:** es la integración más completa: OAuth, EventSub, chat/IRC, moderación y comprobación de bots conocidos.
- **Kick, YouTube y TikTok:** tienen conectores y monitores para recopilar el estado y audiencia de directos, según las credenciales y capacidades disponibles en cada plataforma.
- **Widget web:** permite enviar huellas y eventos desde un sitio propio, complementando los datos que ofrecen las plataformas.

## Componentes principales

| Componente | Tecnología | Función |
| --- | --- | --- |
| Panel web | Next.js, React y Tailwind | Inicio de sesión, configuración de canales, SOC, alertas, vistas de IA e informes |
| API | FastAPI (Python) | Autenticación, endpoints, recepción de webhooks/eventos y reglas de negocio |
| Tiempo real | Redis Streams y Pub/Sub, WebSocket | Cola de trabajo y actualización inmediata del panel |
| Base de datos | PostgreSQL (Neon en producción) | Usuarios, canales, eventos, sesiones, ataques, alertas y mitigaciones |
| IA y clasificación | scikit-learn y Weka J48 | Detección de anomalías y clasificación de actividad sospechosa |
| Datos opcionales | MongoDB | Archivo/analítica de alto volumen y datos de inteligencia de amenazas |
| Observabilidad | Prometheus, Loki y Grafana compatibles | Métricas, registros y supervisión operativa |

## Qué ve una persona que usa el panel

Después de iniciar sesión y conectar un canal, el área **SOC Command Center** muestra, entre otras cosas:

- ataques y alertas activos;
- mapa y línea de tiempo de amenazas;
- eventos recientes y espectadores sospechosos;
- estado de los monitores de plataforma;
- bots conocidos detectados;
- inteligencia de amenazas, flujo de audiencia, huellas digitales y predicciones de IA;
- acciones aplicadas y registros de bloqueos.

No todas las pantallas requieren ni garantizan que una integración externa esté configurada: los datos disponibles dependen de las credenciales, permisos y opciones activadas en el entorno.

## Seguridad incorporada

La API aplica varias capas de protección: autenticación con JWT, cookies de renovación, protección CSRF, límites de solicitudes, validación de cabeceras, protección contra repetición de peticiones y políticas por IP/red. Las comunicaciones del panel usan HTTPS y WebSocket seguro (`WSS`) en producción.

Las claves de Twitch, YouTube, Kick, bases de datos y servicios de reputación deben estar únicamente en variables de entorno del despliegue. No deben subirse al repositorio ni copiarse a documentación pública.

## Dónde está cada parte del código

```text
frontend/                         Panel web Next.js
backend/app/main.py               Punto de entrada de la API FastAPI
backend/app/api/v1/               Endpoints de la API
backend/app/services/detection/   Reglas de detección y huellas
backend/app/services/mitigation/  Bloqueos y acciones de respuesta
backend/app/events/               Cola, procesamiento y publicación de eventos
backend/app/integrations/         Twitch, Kick, YouTube, TikTok y threat intel
backend/app/ai_intel/             Modelos, inferencia y aprendizaje
backend/app/infrastructure/       Base de datos, Redis y middleware de seguridad
infrastructure/                   Nginx, Prometheus, Loki y Kubernetes
deploy/                           Configuraciones de despliegue local, VPS y nube
project-docs/                     Documentación técnica complementaria
```

## Despliegue habitual

El diseño previsto separa el panel de la API:

```text
Vercel (frontend) -> Render/VPS (API y workers) -> Neon/PostgreSQL + Upstash/Redis
```

También hay archivos Docker para desarrollo local y despliegues empresariales. Los procesos *worker* permiten mover el procesamiento intensivo fuera de la API cuando hay más eventos.

## Lecturas técnicas relacionadas

- [Arquitectura empresarial](ENTERPRISE-ARCHITECTURE.md): detalle de la arquitectura orientada a escalabilidad.
- [Almacenes de datos](DATA-STORES.md): responsabilidades de PostgreSQL, Redis y MongoDB.
- [Inteligencia artificial](AI-INTELLIGENCE.md): modelos y endpoints de IA.
- [Guía de despliegue](../DEPLOYMENT_GUIDE.md): pasos para poner el sistema en marcha.

