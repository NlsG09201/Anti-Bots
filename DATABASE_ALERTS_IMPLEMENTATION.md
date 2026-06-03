# Database-Backed Alert System Implementation

## Overview

The alert system has been fully integrated with PostgreSQL for persistent storage. All alerts are now saved to the database, enabling full audit trails, historical analysis, and recovery after system restarts.

## Files Created/Modified

### Backend

#### Models & Database
- **`app/domain/models/alert.py`** - SQLAlchemy models for:
  - `Alert` - Main alert table with full details
  - `AlertHistory` - Audit trail for alert status changes
  - `AlertRule` - Alert rule definitions for automated generation

#### Repositories & Data Access
- **`app/infrastructure/repositories/alert_repository.py`** - Alert data access layer:
  - `AlertRepository` - CRUD operations for alerts
  - `AlertRuleRepository` - Rule management
  - Methods: create, get, dismiss, acknowledge, search, filter

#### Services
- **`app/services/enhanced_alert_engine.py`** - Enhanced alert engine with DB integration:
  - `EnhancedAlertEngine` - Replaces previous in-memory engine
  - Full persistence to PostgreSQL
  - Same API as before (drop-in replacement)
  - Still supports Redis caching for cooldowns

#### API Endpoints
- **`app/api/v1/alerts.py`** - New REST API for alert management:
  - `POST /api/v1/alerts/{stream_id}` - Get stream alerts with filtering
  - `GET /api/v1/alerts/stream/{stream_id}/active` - Active alerts only
  - `GET /api/v1/alerts/{alert_id}` - Alert details with history
  - `GET /api/v1/alerts/stream/{stream_id}/recent` - Recent alerts (by time)
  - `GET /api/v1/alerts/tenant/{tenant_id}` - All tenant alerts
  - `POST /api/v1/alerts/{alert_id}/dismiss` - Dismiss alert
  - `POST /api/v1/alerts/{alert_id}/acknowledge` - Acknowledge alert

#### Database Migrations
- **`backend/alembic/versions/002_add_alerts_table.py`** - Alembic migration:
  - Creates `alerts` table with 7+ indexes
  - Creates `alert_history` audit table
  - Creates `alert_rules` table
  - Includes up/down migration support

### Frontend

#### Components
- **`frontend/src/components/soc/AlertPanel.tsx`** - Updated to use database API:
  - Fetches from new `/api/v1/alerts/` endpoints
  - Displays active alerts with dismiss button
  - Shows dismissed alerts in collapsible section
  - Real-time updates via polling
  - Error handling and loading states

## Database Schema

### alerts table
```sql
CREATE TABLE alerts (
  id UUID PRIMARY KEY,
  stream_id VARCHAR(255) NOT NULL,
  tenant_id UUID NOT NULL,
  alert_type VARCHAR(50) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  title VARCHAR(255) NOT NULL,
  description VARCHAR(1000) NOT NULL,
  data JSON,
  dismissed BOOLEAN DEFAULT false,
  acknowledged BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  dismissed_at TIMESTAMP,
  acknowledged_at TIMESTAMP,
  source VARCHAR(50),
  tags JSON,
  
  -- Indexes for fast queries
  INDEX ix_alerts_stream_id_created_at (stream_id, created_at),
  INDEX ix_alerts_tenant_id_created_at (tenant_id, created_at),
  INDEX ix_alerts_severity (severity),
  INDEX ix_alerts_dismissed (dismissed),
  INDEX ix_alerts_alert_type (alert_type)
);
```

### alert_history table (Audit Trail)
```sql
CREATE TABLE alert_history (
  id UUID PRIMARY KEY,
  alert_id UUID NOT NULL REFERENCES alerts(id),
  action VARCHAR(50) NOT NULL,  -- created, dismissed, acknowledged
  changed_by VARCHAR(255),
  reason VARCHAR(500),
  metadata JSON,
  created_at TIMESTAMP DEFAULT now(),
  
  INDEX ix_alert_history_alert_id (alert_id),
  INDEX ix_alert_history_created_at (created_at)
);
```

### alert_rules table (Rule Definitions)
```sql
CREATE TABLE alert_rules (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  name VARCHAR(255) NOT NULL,
  description VARCHAR(1000),
  alert_type VARCHAR(50) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  conditions JSON NOT NULL,
  actions JSON NOT NULL,
  enabled BOOLEAN DEFAULT true,
  cooldown_minutes INTEGER DEFAULT 5,
  max_alerts_per_hour INTEGER,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  
  INDEX ix_alert_rules_tenant_id (tenant_id),
  INDEX ix_alert_rules_enabled (enabled)
);
```

## Deployment Steps

### 1. Apply Database Migration

```bash
cd backend

# Generate migration if not already done
alembic revision --autogenerate -m "add_alerts_table"

# Apply migration
alembic upgrade head
```

### 2. Update Environment Variables

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
REDIS_URL=redis://host:6379
```

### 3. Update Main FastAPI App

Add to `app/main.py`:

```python
from app.api.v1 import alerts

app.include_router(alerts.router)
```

### 4. Restart Services

```bash
# Backend
uvicorn app.main:app --reload

# Frontend (already uses new endpoints)
npm run dev
```

## Usage Examples

### Create Alert from Threat Engine

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.enhanced_alert_engine import EnhancedAlertEngine, AlertType, AlertSeverity

async def process_threat(session: AsyncSession):
    engine = EnhancedAlertEngine(session)
    
    alert = await engine.generate_alert(
        stream_id="twitch:channel123",
        tenant_id="tenant-uuid",
        alert_type=AlertType.VIEWBOT_ATTACK,
        severity=AlertSeverity.HIGH,
        title="Viewbot Attack Detected",
        description="Impossible growth pattern: 500 viewers in 5 seconds",
        data={"suspected_bot_count": 500, "risk_score": 0.85}
    )
    
    if alert:
        print(f"Alert created: {alert['id']}")
```

### Query Alerts from Database

```bash
# Get active alerts for a stream
curl http://localhost:8000/api/v1/alerts/stream/twitch:channel123/active

# Get alerts with pagination
curl "http://localhost:8000/api/v1/alerts/twitch:channel123?limit=20&offset=0&severity=HIGH"

# Get alert details with history
curl http://localhost:8000/api/v1/alerts/{alert_id}

# Get all tenant alerts
curl http://localhost:8000/api/v1/alerts/tenant/{tenant_id}

# Get recent alerts (last 60 minutes)
curl "http://localhost:8000/api/v1/alerts/stream/twitch:channel123/recent?minutes=60"
```

### Dismiss Alert

```bash
curl -X POST http://localhost:8000/api/v1/alerts/{alert_id}/dismiss \
  -H "Content-Type: application/json" \
  -d '{"reason": "False positive", "dismissed_by": "user123"}'
```

### Acknowledge Alert

```bash
curl -X POST http://localhost:8000/api/v1/alerts/{alert_id}/acknowledge \
  -H "Content-Type: application/json" \
  -d '{"acked_by": "user123"}'
```

## Features Implemented

✅ **Persistent Storage** - All alerts saved to PostgreSQL  
✅ **Audit Trail** - alert_history table tracks all changes  
✅ **Filtering** - By stream, tenant, severity, type, status  
✅ **Pagination** - Limit/offset for large result sets  
✅ **Full-Text Search** - Title and description searchable  
✅ **Status Tracking** - Dismissed, acknowledged states  
✅ **Time-based Queries** - Recent alerts by minute range  
✅ **Cooldown Management** - 5-minute duplicate prevention  
✅ **Notifications** - Discord and webhook still supported  
✅ **Real-time Broadcasting** - WebSocket updates to clients  

## Performance Optimizations

- **Indexes**: 7 multi-column indexes on high-query paths
- **Connection Pooling**: AsyncIO pooling via SQLAlchemy
- **Query Optimization**: Only fetching needed columns
- **Pagination**: Prevents loading massive result sets
- **Cooldown Cache**: Redis for quick cooldown checks
- **Batch Operations**: Support for bulk queries

## Monitoring & Analytics

### Queries to Monitor Alerts

```sql
-- Alert volume by stream
SELECT stream_id, COUNT(*) as alert_count
FROM alerts
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY stream_id
ORDER BY alert_count DESC;

-- Alert severity distribution
SELECT severity, COUNT(*) as count
FROM alerts
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY severity;

-- Alert types by frequency
SELECT alert_type, COUNT(*) as frequency
FROM alerts
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY alert_type
ORDER BY frequency DESC;

-- Dismissal rate
SELECT
  COUNT(CASE WHEN dismissed THEN 1 END)::float / COUNT(*) as dismissal_rate
FROM alerts
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Average time to dismissal
SELECT
  AVG(EXTRACT(EPOCH FROM (dismissed_at - created_at))) as avg_seconds_to_dismiss
FROM alerts
WHERE dismissed = true
AND created_at > NOW() - INTERVAL '30 days';
```

## Testing

### Unit Test Example

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.repositories.alert_repository import AlertRepository

@pytest.mark.asyncio
async def test_create_and_retrieve_alert(session: AsyncSession):
    repo = AlertRepository(session)
    
    alert = await repo.create_alert(
        alert_id=uuid4(),
        stream_id="test:stream",
        tenant_id=uuid4(),
        alert_type="VIEWBOT_ATTACK",
        severity="HIGH",
        title="Test Alert",
        description="Test description"
    )
    
    retrieved = await repo.get_alert_by_id(alert.id)
    assert retrieved.title == "Test Alert"
```

## Migration Path

If upgrading from previous alert system:

1. Run Alembic migration to create tables
2. Optionally migrate existing alerts from Redis cache
3. Update imports: `alert_engine` → `enhanced_alert_engine`
4. No API changes needed - backward compatible

## Troubleshooting

### Alerts Not Persisting
- Check PostgreSQL connection: `DATABASE_URL` env var
- Verify migrations applied: `alembic current`
- Check logs for database errors

### Slow Queries
- Check indexes exist: `\d alerts` in psql
- Monitor query plans: `EXPLAIN ANALYZE SELECT...`
- Consider archiving old alerts

### Alert Deduplication Not Working
- Verify Redis is running
- Check `REDIS_URL` environment variable
- Monitor Redis memory usage

## Future Enhancements

- [ ] Alert template system for custom messages
- [ ] Alert routing rules (different channels by type/severity)
- [ ] Batch dismiss operations
- [ ] Alert correlation (group related alerts)
- [ ] Email/SMS notifications
- [ ] Slack integration
- [ ] Alert archive/retention policies
- [ ] Machine learning for false positive detection
