# Power BI Integration Guide — Anti-Bots SOC

## Overview

La plataforma Anti-Bots SOC proporciona integración completa con Microsoft Power BI para crear dashboards interactivos en tiempo real.

## Endpoints REST Disponibles

### Global Metrics
```
GET /api/v1/power-bi/metrics/global
```
Retorna métricas globales del SOC:
- Streams monitoreados
- Viewers sospechosos
- Ataques detectados
- Threat score global

### KPIs
```
GET /api/v1/power-bi/metrics/kpis
```
Retorna KPIs principales:
- Real engagement %
- Bot detection rate
- Threat mitigation rate
- Platform health score
- Response time promedio

### Stream Snapshots
```
GET /api/v1/power-bi/streams/snapshots?platform=kick&limit=100
```
Obtiene snapshots de streams activos con:
- Viewer counts
- Engagement scores
- Threat scores
- Attack counts

### Suspicious Viewers
```
GET /api/v1/power-bi/viewers/suspicious?min_score=0.7&limit=1000
```
Lista de viewers sospechosos con:
- Bot probability
- Suspicious patterns
- Cross-platform hits

### Attacks
```
GET /api/v1/power-bi/attacks/list?status=active&hours=24
```
Ataques detectados con:
- Attack type
- Severity
- Bots involved
- Mitigation action

### Export Dataset
```
GET /api/v1/power-bi/dataset/json?tables=all
```
Dataset completo en JSON para importar en Power BI

### Export Data
```
POST /api/v1/power-bi/export
{
  "format": "csv|excel|json",
  "table_type": "streams|suspicious_viewers|attacks|engagement|ai_predictions|all",
  "date_from": "2024-01-01T00:00:00Z",
  "date_to": "2024-01-31T23:59:59Z"
}
```

## Conexión a Power BI

### Método 1: API REST Direct

1. **Abrir Power BI Desktop**
2. **Home → Get Data → Web**
3. **Ingresar URL del endpoint**:
   ```
   https://anti-bots.vercel.app/api/v1/power-bi/metrics/global
   ```
4. **Authentication → Organizational Account**
5. **Ingresar credenciales de tenant**
6. **OK → Power BI cargará los datos automáticamente**

### Método 2: JSON Export

1. **Descargar dataset JSON**:
   ```bash
   curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://anti-bots.vercel.app/api/v1/power-bi/dataset/json"
   ```
2. **Power BI → Get Data → JSON**
3. **Seleccionar archivo descargado**

### Método 3: CSV Export

1. **Exportar CSV desde API**:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"format":"csv","table_type":"streams"}' \
     "https://anti-bots.vercel.app/api/v1/power-bi/export"
   ```
2. **Power BI → Get Data → CSV**
3. **Transformar y cargar datos**

## Modelos de Datos

### Tabla: Streams
```
StreamID (PK)           → Identificador único del stream
TenantID                → ID del tenant
Platform                → twitch, kick, youtube, tiktok
ChannelName             → Nombre del canal
IsLive                  → Estado live/offline
ViewerCount             → Viewers actuales
ViewerCountPeak         → Viewers máximos (24h)
EngagementScore         → Score de engagement (0-100)
ThreatScore             → Score de amenaza (0-1)
BotProbability          → Probabilidad de bots (0-1)
ActiveAttacks           → Ataques activos
SuspiciousViewers       → Count de viewers sospechosos
MessagesPerMinute       → Mensajes/minuto
FollowsPerMinute        → Follows/minuto
GiftsPerMinute          → Gifts/minuto
LastUpdated             → Timestamp del último update
CreatedDate             → Fecha de creación del stream
```

**Relaciones:**
- Streams → SuspiciousViewers (1-N)
- Streams → Attacks (1-N)

### Tabla: SuspiciousViewers
```
ViewerID (PK)           → Identificador único
Username                → Nombre de usuario
StreamID (FK)           → Referencia a Streams
Platform                → Plataforma del viewer
BotProbability          → Probabilidad bot (0-1)
SuspiciousScore         → Score sospechoso (0-1)
TrustScore              → Score confianza (0-100)
FirstSeen               → Primera vez visto
LastSeen                → Última vez visto
AccountAgeDays          → Edad de la cuenta (días)
InteractionCount        → Total interacciones
MessageCount            → Mensajes enviados
FollowsCount            → Follows realizados
RiskLevel               → low, medium, high, critical
CrossPlatformHits       → Hits en otras plataformas
```

### Tabla: Attacks
```
AttackID (PK)           → Identificador único
StreamID (FK)           → Referencia a Streams
TenantID                → ID del tenant
AttackType              → viewbotting, followbotting, raid, spam, synthetic
Severity                → low, medium, high, critical
Status                  → active, mitigated, resolved
DetectedAt              → Timestamp de detección
Duration                → Duración en segundos
BotsInvolved            → Cantidad de bots
ViewersAffected         → Viewers afectados
EngagementImpact        → Impacto en engagement (%)
ConfidenceScore         → Confianza de detección (0-1)
MitigationAction        → Acción tomada
```

### Tabla: Engagement
```
StreamID (FK)           → Referencia a Streams
Platform                → Plataforma
Period                  → 1h, 24h, 7d, 30d
TotalViewers            → Total viewers en período
UniqueChatters          → Chatters únicos
MessagesTotal           → Total mensajes
FollowsTotal            → Total follows
GiftsTotal              → Total gifts
EngagementRate          → Rate de engagement (%)
RetentionRate           → Rate de retención (%)
RealEngagementScore     → Score de engagement real
SyntheticEngagementScore→ Score engagement sintético
```

## Medidas DAX Recomendadas

### Engagement Rate
```dax
EngagementRate = 
    DIVIDE(
        SUM(Engagement[MessagesTotal]),
        SUM(Streams[ViewerCount]),
        0
    ) * 100
```

### Bot Detection Rate
```dax
BotDetectionRate = 
    DIVIDE(
        COUNTROWS(
            FILTER(SuspiciousViewers, 
                   [BotProbability] > 0.7)
        ),
        COUNTROWS(SuspiciousViewers),
        0
    ) * 100
```

### Average Threat Score
```dax
AvgThreatScore = 
    AVERAGE(Streams[ThreatScore]) * 100
```

### Active Attack Count
```dax
ActiveAttackCount = 
    COUNTROWS(
        FILTER(Attacks, [Status] = "active")
    )
```

### Synthetic Audience %
```dax
SyntheticAudiencePercent = 
    DIVIDE(
        SUMPRODUCT(Streams[ViewerCount] * Streams[BotProbability]),
        SUM(Streams[ViewerCount]),
        0
    ) * 100
```

## Dashboard Recomendado

### Página 1: SOC Overview
- **KPI Cards**: Threat score, Active attacks, Bot detection rate
- **Line Chart**: Threat score tendencia (últimas 24h)
- **Gauge Chart**: Health score
- **Table**: Top 10 streams por threat score

### Página 2: Live Streaming Analytics
- **Line Chart**: Viewer count por stream
- **Stacked Bar Chart**: Engagement breakdown (real vs synthetic)
- **Table**: Live streams con engagement rates
- **Map**: Streams por geografía (si está disponible)

### Página 3: Threat Intelligence
- **Pie Chart**: Attack types distribution
- **Timeline**: Ataques en el tiempo
- **Table**: Attacks con severidad
- **Treemap**: Top platforms por ataques

### Página 4: Suspicious Viewers
- **Scatter Plot**: Bot probability vs trust score
- **Bar Chart**: Risk level distribution
- **Table**: Suspicious viewers con flags
- **KCard**: Total suspicious viewers activos

### Página 5: Cross-Platform Analysis
- **Column Chart**: Viewers por plataforma
- **Line Chart**: Threat score por plataforma
- **Matrix**: Platform × Attack Type
- **Donut Chart**: Distribution de streams

### Página 6: Executive KPIs
- **KPI Cards**: Real engagement %, Bot %, Mitigation rate
- **Gauge Charts**: Health scores
- **Line Charts**: Tendencias principales
- **Trend indicators**: Up/down con porcentajes

## Configuración de Refresh

### Real-time (Recomendado)
```
Power BI Service → Settings → Refresh
Schedule: Every 10 minutes
```

### High Latency
```
Schedule: Every 30 minutes
```

### Nightly Refresh
```
Schedule: Daily a las 2 AM
```

## Filtros Recomendados

### Slicers en Dashboard
- **Platform**: twitch, kick, youtube, tiktok
- **Date Range**: Últimas 24h, 7 días, 30 días
- **Threat Level**: low, medium, high, critical
- **Status**: active, mitigated, resolved

## Alertas en Power BI

### Alertas Recomendadas
1. **High Threat Score**: > 0.8
2. **Multiple Active Attacks**: > 5
3. **Sudden Viewer Spike**: +50% en 5 min
4. **Suspicious Bot Cluster**: > 100 bots en 5 min

### Configuración
```
Power BI Service → Datasets → Configurar alertas
Threshold: Personalizable por métrica
Recipients: Email notifications
```

## URLs Estáticas

```
Global Dashboard:
https://anti-bots.vercel.app/power-bi

API Root:
https://anti-bots.vercel.app/api/v1/power-bi

Swagger API Docs:
https://anti-bots.vercel.app/docs#/Power%20BI
```

## Autenticación

Todos los endpoints requieren autenticación JWT.

```bash
# Obtener token
curl -X POST https://anti-bots.vercel.app/auth/login \
  -d '{"email":"user@example.com","password":"..."}'

# Usar en headers
curl -H "Authorization: Bearer $TOKEN" \
  "https://anti-bots.vercel.app/api/v1/power-bi/metrics/global"
```

## Excel/CSV Export

### Descargar CSV
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "csv",
    "table_type": "streams",
    "date_from": "2024-01-01T00:00:00Z",
    "date_to": "2024-01-31T23:59:59Z"
  }' \
  "https://anti-bots.vercel.app/api/v1/power-bi/export" \
  > streams.csv
```

### Descargar Excel
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "excel",
    "table_type": "all"
  }' \
  "https://anti-bots.vercel.app/api/v1/power-bi/export" \
  > anti-bots-export.xlsx
```

## Troubleshooting

### Conexión rechazada
- Verificar que el token sea válido
- Verificar CORS en configuración del backend
- Verificar que la URL sea correcta

### Datos vacíos
- Verificar que existan streams activos
- Revisar los filtros aplicados
- Verificar los permisos del tenant

### Refresh lento
- Reducir el rango de fechas
- Limitar cantidad de rows
- Usar agregaciones en lugar de datos raw

## Support

Para soporte técnico:
```
Email: support@anti-bots.app
Slack: #power-bi-support
Docs: https://docs.anti-bots.app/power-bi
```
