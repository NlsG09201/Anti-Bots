# Advanced Streaming Threat Intelligence Engine - Deployment Guide

## Quick Start

### Development Environment

```bash
# 1. Clone and setup backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file with configuration
cp .env.threat_intel .env

# 4. Start Redis (required)
redis-server

# 5. Start FastAPI server
uvicorn app.main:app --reload --port 8000

# 6. In another terminal, install and start frontend
cd ../frontend
npm install
npm run dev
```

### Docker Deployment

#### Backend Service

```dockerfile
# Dockerfile.threat-intel
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    geoip-bin \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend /app

# Download GeoIP databases
RUN mkdir -p /data && \
    curl -L https://geolite.maxmind.com/download/geoip/databases/GeoLite2-City/GeoLite2-City.mmdb \
    -o /data/GeoLite2-City.mmdb

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  threat-intel-backend:
    build:
      context: .
      dockerfile: Dockerfile.threat-intel
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - MONGODB_URI=${MONGODB_URI}
      - IPINFO_API_KEY=${IPINFO_API_KEY}
      - ABUSEIPDB_API_KEY=${ABUSEIPDB_API_KEY}
      - THREAT_INTEL_ENGINE_ENABLED=true
      - AI_INTEL_ENABLED=true
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://threat-intel-backend:8000
    depends_on:
      - threat-intel-backend

volumes:
  redis_data:
```

#### Deploy with Docker Compose

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f threat-intel-backend

# Scale backend
docker-compose up -d --scale threat-intel-backend=3

# Stop services
docker-compose down
```

### Kubernetes Deployment

#### Backend Deployment

```yaml
# k8s/threat-intel-backend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: threat-intel-backend
  labels:
    app: threat-intel-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: threat-intel-backend
  template:
    metadata:
      labels:
        app: threat-intel-backend
    spec:
      containers:
      - name: api
        image: anti-bots/threat-intel-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: threat-intel-config
              key: redis_url
        - name: MONGODB_URI
          valueFrom:
            secretKeyRef:
              name: threat-intel-secrets
              key: mongodb_uri
        - name: IPINFO_API_KEY
          valueFrom:
            secretKeyRef:
              name: threat-intel-secrets
              key: ipinfo_api_key
        - name: ABUSEIPDB_API_KEY
          valueFrom:
            secretKeyRef:
              name: threat-intel-secrets
              key: abuseipdb_api_key
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: threat-intel-backend-service
spec:
  selector:
    app: threat-intel-backend
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
```

#### Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace threat-intel

# Create secrets
kubectl create secret generic threat-intel-secrets \
  --from-literal=mongodb_uri=$MONGODB_URI \
  --from-literal=ipinfo_api_key=$IPINFO_API_KEY \
  --from-literal=abuseipdb_api_key=$ABUSEIPDB_API_KEY \
  -n threat-intel

# Create config map
kubectl create configmap threat-intel-config \
  --from-literal=redis_url=redis://redis-service:6379 \
  -n threat-intel

# Deploy
kubectl apply -f k8s/threat-intel-backend.yaml -n threat-intel

# Check deployment
kubectl get deployments -n threat-intel
kubectl get pods -n threat-intel
kubectl logs -f deployment/threat-intel-backend -n threat-intel
```

### Production Setup (Render)

#### Render Deployment File

```yaml
# render.yaml (threat-intel section)
services:
  - type: web
    name: threat-intel-api
    env: python
    plan: standard
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    autoDeploy: false
    envVars:
      - key: PYTHON_VERSION
        value: "3.11"
      - key: THREAT_INTEL_ENGINE_ENABLED
        value: "true"
      - key: REDIS_URL
        fromService:
          type: redis
          name: threat-intel-redis
          property: connectionString
      - key: MONGODB_URI
        sync: false
      - key: IPINFO_API_KEY
        sync: false
      - key: ABUSEIPDB_API_KEY
        sync: false

  - type: redis
    name: threat-intel-redis
    plan: standard
    ipAllowList: []  # Allow all IPs

  - type: web
    name: threat-intel-dashboard
    env: node
    plan: standard
    buildCommand: "npm install && npm run build"
    startCommand: "npm start"
    envVars:
      - key: NEXT_PUBLIC_API_URL
        fromService:
          type: web
          name: threat-intel-api
          property: renderURL
```

#### Deploy to Render

```bash
# Link to Render
render login

# Deploy
render deploy --project threat-intel-api

# View logs
render logs threat-intel-api

# Monitor
render status threat-intel-api
```

## Configuration

### Environment Variables

```bash
# Required for threat intelligence
IPINFO_API_KEY=your_ipinfo_key
ABUSEIPDB_API_KEY=your_abuseipdb_key
VIRUSTOTAL_API_KEY=your_virustotal_key

# Databases
REDIS_URL=redis://localhost:6379
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/threat_intel

# GeoIP Databases
MAXMIND_CITY_DB_PATH=/data/GeoLite2-City.mmdb
MAXMIND_ASN_DB_PATH=/data/GeoLite2-ASN.mmdb

# Features
THREAT_INTEL_ENGINE_ENABLED=true
AI_INTEL_ENABLED=true
TOR_DETECTION_ENABLED=true
SPAMHAUS_ENABLED=true

# Alerts
DISCORD_WEBHOOK_URL=your_discord_webhook
ALERT_WEBHOOK_URLS=https://example.com/webhook1,https://example.com/webhook2
```

## Database Setup

### MongoDB

```bash
# Create database
use streaming_threat_intel

# Create collections
db.createCollection("threat_assessments", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["stream_id", "timestamp"],
      properties: {
        stream_id: { bsonType: "string" },
        timestamp: { bsonType: "int" },
        overall_risk_score: { bsonType: "double" },
        threat_components: { bsonType: "object" }
      }
    }
  }
})

db.createCollection("alerts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["stream_id", "timestamp"],
      properties: {
        stream_id: { bsonType: "string" },
        timestamp: { bsonType: "int" },
        severity: { enum: ["CRITICAL", "HIGH", "MEDIUM", "LOW"] }
      }
    }
  }
})

# Create indexes
db.threat_assessments.createIndex({ stream_id: 1, timestamp: -1 })
db.threat_assessments.createIndex({ overall_risk_score: -1 })
db.alerts.createIndex({ stream_id: 1, timestamp: -1 })
db.alerts.createIndex({ severity: 1 })
```

### Redis

```bash
# Key patterns
ti:ip:{ip_address}:full          # Full IP assessment (1h TTL)
net_rep:{ip_address}             # Reputation score (24h TTL)
ti:stream:{stream_id}:*          # Stream-specific data
ss:ai:rep:*                      # AI reputation data
threat:stream:{stream_id}:*      # Stream threat data
alert:{stream_id}:{alert_id}     # Alert data (24h TTL)
```

## Monitoring

### Prometheus Metrics

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'threat-intel'
    static_configs:
      - targets: ['localhost:9090']
```

### Key Metrics to Monitor

```
# Request metrics
http_requests_total{method="POST",endpoint="/assess-stream"}
http_request_duration_seconds{endpoint="/assess-stream"}

# Threat metrics
threat_scores_by_stream
detected_attacks_total
false_positive_rate

# API performance
ip_assessment_latency_seconds
batch_assessment_duration_seconds
```

### Grafana Dashboard

Create dashboards for:
- Overall threat level by stream
- Attack frequency by type
- IP threat distribution
- API response times
- Cache hit rates
- Alert volume

## Scaling Considerations

### Horizontal Scaling

```bash
# Scale backend to 5 instances
docker-compose up -d --scale threat-intel-backend=5

# Or with Kubernetes
kubectl scale deployment threat-intel-backend --replicas=5 -n threat-intel
```

### Performance Optimization

```python
# Batch assessment settings
BATCH_SIZE=100
MAX_CONCURRENT_ASSESSMENTS=50

# Cache optimization
CACHE_TTL=3600  # 1 hour for IP assessments
LONG_TERM_CACHE_TTL=2592000  # 30 days for historical data

# Timeouts
IP_ASSESSMENT_TIMEOUT=10  # seconds
BEHAVIORAL_ANALYSIS_TIMEOUT=5  # seconds
```

## Troubleshooting

### Common Issues

1. **High API latency**
   - Check Redis connection
   - Verify API key rate limits
   - Enable IP caching
   - Scale horizontally

2. **High false positive rate**
   - Adjust threat score thresholds
   - Increase historical data window
   - Fine-tune pattern detection sensitivity
   - Add whitelisting rules

3. **WebSocket disconnections**
   - Check WebSocket URL (wss vs ws)
   - Verify CORS configuration
   - Monitor network connectivity
   - Implement client-side reconnection

### Debugging

```bash
# Check logs
docker-compose logs -f threat-intel-backend

# Test API
curl http://localhost:8000/api/v1/threat-intelligence/assess-ip?ip_address=1.2.3.4

# Check Redis
redis-cli
> KEYS ti:ip:*
> GET ti:ip:1.2.3.4:full

# Test WebSocket
wscat -c ws://localhost:8000/api/v1/threat-intelligence/ws/stream-threat/test-stream
```

## Maintenance

### Daily Tasks
- Monitor alert volume
- Check for API failures
- Verify cache hit rates

### Weekly Tasks
- Review false positive reports
- Update threat lists (TOR nodes, etc.)
- Check database growth

### Monthly Tasks
- Retrain anomaly models
- Review and adjust thresholds
- Backup threat assessment data
- Analyze effectiveness metrics

## Security

### API Security
- Enable rate limiting
- Use API keys for all external APIs
- Implement request signing for webhooks
- Use HTTPS/WSS only in production

### Data Security
- Encrypt sensitive data in transit (TLS)
- Encrypt sensitive data at rest (MongoDB)
- Implement access controls (IAM)
- Regular security audits

### Best Practices
- Never commit API keys to git
- Use environment variables for secrets
- Implement request validation
- Log security events
- Monitor for suspicious API usage
