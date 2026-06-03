# Advanced Streaming Threat Intelligence Engine - Integration Guide

## Overview

This is a comprehensive threat intelligence system for detecting bots, fraud, and automated attacks on streaming platforms (Twitch, YouTube Live, TikTok, Kick).

## Architecture

### Backend Services

1. **Threat Intelligence Aggregator** (`app/integrations/threat_intel/aggregator.py`)
   - Unified IP threat assessment combining multiple sources
   - Real-time IP reputation scoring
   - Batch IP analysis for efficiency

2. **Network Reputation Scorer** (`app/ai_intel/reputation/network_score.py`)
   - VPN/Proxy/Datacenter/TOR detection scoring
   - Multi-dimensional threat assessment
   - Reputation decay over time

3. **Behavioral Analyzer** (`app/threat_intel_engine/behavioral_advanced.py`)
   - Real-time pattern detection
   - Synchronized viewer detection
   - Impossible growth detection
   - Mass entry detection
   - Silent viewer analysis

4. **Chat Intelligence Engine** (`app/threat_intel_engine/chat_intelligence.py`)
   - Message repetition detection
   - Automation pattern recognition
   - Spam detection
   - Coordinated spam identification
   - Semantic similarity analysis

5. **Threat Correlation Engine** (`app/services/threat_correlation.py`)
   - Combines all threat components
   - Real-time risk scoring
   - Attack detection
   - Recommendations generation

### Frontend Dashboard

SOC Dashboard with real-time threat visualization:
- Main dashboard (`src/components/soc/SOCDashboard.tsx`)
- Threat metrics (`src/components/soc/ThreatMetrics.tsx`)
- Suspicious viewers (`src/components/soc/ThreatViewer.tsx`)
- Attack timeline (`src/components/soc/AttackTimeline.tsx`)
- Alert panel (`src/components/soc/AlertPanel.tsx`)
- Geolocation map (`src/components/soc/ThreatMap.tsx`)

## Environment Configuration

### Backend Configuration (.env)

```env
# Threat Intelligence API Keys
IPINFO_API_KEY=your_ipinfo_api_key
ABUSEIPDB_API_KEY=your_abuseipdb_api_key
VIRUSTOTAL_API_KEY=your_virustotal_api_key

# GeoIP Databases (must download separately)
GEOIP_DATABASE_PATH=/data/GeoLite2-City.mmdb
MAXMIND_CITY_DB_PATH=/data/GeoLite2-City.mmdb
MAXMIND_ASN_DB_PATH=/data/GeoLite2-ASN.mmdb
IP2LOCATION_DB_PATH=/data/IP2LOCATION-LITE-DB5.CSV

# Threat Intelligence Features
THREAT_INTEL_ENGINE_ENABLED=true
AI_INTEL_ENABLED=true
TOR_DETECTION_ENABLED=true
SPAMHAUS_ENABLED=true

# Redis & Cache
REDIS_URL=redis://localhost:6379
CACHE_TTL=3600

# MongoDB Atlas (for threat logs)
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/streaming_threat_intel
```

## Installation & Setup

### 1. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

Required packages:
```
fastapi==0.115.6
sklearn
pandas
numpy
networkx
geoip2
IP2Location
httpx
```

### 2. Download GeoIP Databases

MaxMind GeoLite2 (Free):
```bash
# Visit: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/
# Download GeoLite2-City and GeoLite2-ASN
# Place in /backend/data/
```

IP2Location (Optional):
```bash
# Download IP2LOCATION-LITE-DB5 from https://www.ip2location.com/
# Place in /backend/data/
```

### 3. Configure Threat Intelligence APIs

#### IPInfo Setup
```bash
# Sign up at https://ipinfo.io
# Get API key and add to .env
IPINFO_API_KEY=your_token
```

#### AbuseIPDB Setup
```bash
# Sign up at https://www.abuseipdb.com/api
# Get API key and add to .env
ABUSEIPDB_API_KEY=your_key
```

#### VirusTotal Setup
```bash
# Sign up at https://www.virustotal.com
# Get API key and add to .env
VIRUSTOTAL_API_KEY=your_key
```

### 4. Setup Redis Cache

```bash
# Local development
redis-server

# Or use Upstash (cloud):
REDIS_URL=redis://:password@host:port
```

### 5. Setup MongoDB Atlas

```bash
# Create cluster at https://www.mongodb.com/
# Create database and collection
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/streaming_threat_intel
```

## API Endpoints

### Threat Intelligence Assessment

#### Assess Stream Threat
```
POST /api/v1/threat-intelligence/assess-stream/{stream_id}

Request:
{
  "tenant_id": "uuid",
  "viewers_data": [
    {
      "viewer_id": "v1",
      "ip_address": "1.2.3.4",
      "fingerprint": "fp_hash",
      "platform_user_id": "user123",
      "username": "username"
    }
  ],
  "recent_messages": [
    {
      "user_id": "u1",
      "username": "user",
      "message": "text",
      "timestamp": 1234567890
    }
  ]
}

Response:
{
  "stream_id": "string",
  "overall_risk_score": 0.75,
  "viewer_count": 500,
  "detected_attacks": ["VIEWBOT_ATTACK", "CHAT_SPAM_ATTACK"],
  "threat_components": {
    "ip_threats": {
      "threat_score": 0.8,
      "suspicious_ips": 45,
      "threat_categories": ["vpn", "datacenter"]
    },
    "behavioral": {
      "behavioral_threat_score": 0.65,
      "patterns_detected": ["synchronized_entries", "impossible_growth"]
    },
    "chat": {
      "chat_threat_score": 0.70,
      "spam_indicators": 12,
      "coordinated_spam_detected": true
    },
    "graph_correlation": {
      "graph_threat_score": 0.5,
      "detected_clusters": 3,
      "coordination_score": 0.55
    }
  },
  "recommendations": [
    "BLOCK_SUSPICIOUS_IPS",
    "ENABLE_SLOW_MODE",
    "MONITOR_VIEWERS"
  ]
}
```

#### Assess IP Threat
```
POST /api/v1/threat-intelligence/assess-ip?ip_address=1.2.3.4

Response:
{
  "ip_address": "1.2.3.4",
  "combined_threat_score": 0.75,
  "recommendation": "STRICT_MONITOR",
  "sources": {
    "abuseipdb": {
      "abuse_confidence": 85,
      "is_tor": false,
      "is_datacenter": true
    },
    "ipinfo": {
      "is_vpn": true,
      "is_proxy": false,
      "country_code": "US"
    },
    "maxmind": {
      "is_tor_exit_node": false,
      "is_datacenter_proxy": true,
      "country_code": "US"
    }
  },
  "threats": ["vpn", "datacenter"],
  "risk_scores": {
    "abuseipdb": 0.85,
    "ipinfo": 0.7,
    "maxmind": 0.65
  }
}
```

#### Get IP Reputation
```
GET /api/v1/threat-intelligence/reputation/{ip_address}

Response:
{
  "ip_address": "1.2.3.4",
  "reputation_score": 35.5,
  "threat_score": 64.5,
  "dimension_scores": {
    "vpn_score": 75.0,
    "proxy_score": 45.0,
    "datacenter_score": 60.0,
    "tor_score": 10.0
  },
  "recommendation": "BLOCK_SUSPICIOUS_PATTERNS",
  "confidence": 0.87
}
```

### Real-time WebSocket

#### Stream Threat Updates
```
WebSocket /api/v1/threat-intelligence/ws/stream-threat/{stream_id}?tenant_id={tenant_id}

Real-time stream threat updates:
{
  "stream_id": "uuid",
  "overall_risk_score": 0.75,
  "viewer_count": 500,
  "detected_attacks": ["VIEWBOT_ATTACK"],
  "threat_components": { ... },
  "recommendations": [ ... ],
  "timestamp": 1234567890
}
```

## Detection Capabilities

### IP-Based Threats
- VPN Detection (confidence: 95%+)
- Proxy Detection (residential, datacenter, etc.)
- TOR Node Detection (real-time from Onionoo)
- Datacenter IP Detection (AWS, DigitalOcean, etc.)
- Abuse History (via AbuseIPDB)
- Geographic anomalies

### Behavioral Threats
- **Synchronized Viewers**: Multiple users joining at exact same time
- **Impossible Growth**: Viewers/second exceeding human limitations
- **Mass Entry**: Spike in viewer joins (3x+ increase in 5s)
- **Silent Viewers**: Users with zero interactions
- **Low Uniqueness**: Same users repeatedly joining
- **Entry Rate Anomalies**: Inconsistent join patterns

### Chat-Based Threats
- **Message Repetition**: Exact or similar messages repeated
- **Automation Patterns**: Bot-like message structures
- **Spam Patterns**: Repeated characters, links, phone numbers
- **Coordinated Spam**: Multiple users posting similar messages
- **High Message Rate**: 10+ messages/minute per user
- **Emoji Spam**: Excessive emoji usage

### Attack Types Detected

1. **VIEWBOT_ATTACK**: Fake viewers, impossible growth
2. **MASS_JOIN_ATTACK**: Coordinated viewer joins
3. **COORDINATED_ATTACK**: Multiple coordinated signals
4. **CHAT_SPAM_ATTACK**: Organized spam campaign
5. **FOLLOWBOT_ATTACK**: Coordinated follow activity
6. **RAID_ATTACK**: Coordinated raid pattern (future)

## Real-Time Processing

### Event Flow

```
1. Viewer Join Event
   ↓
2. IP Intelligence Check (async)
   ├── AbuseIPDB
   ├── IPInfo
   ├── MaxMind
   ├── Spamhaus
   └── TOR Check
   ↓
3. Behavior Pattern Detection
   ├── Synchronized Entries
   ├── Impossible Growth
   ├── Mass Entry
   └── Entropy Analysis
   ↓
4. Chat Analysis (if message)
   ├── Spam Detection
   ├── Automation Detection
   └── Coordination Detection
   ↓
5. Graph Correlation
   ├── Build correlation edges
   └── Detect clusters
   ↓
6. Reputation Scoring
   ├── Multi-dimensional scoring
   └── Risk aggregation
   ↓
7. Assessment Generation
   ├── Overall risk score
   ├── Recommendations
   └── WebSocket broadcast
```

### Performance Optimization

- **IP Cache**: 1 hour caching for IP assessments
- **Batch Processing**: Assess 100s of IPs simultaneously
- **Redis**: Fast reputation lookups
- **MongoDB**: Long-term threat history
- **WebSocket**: Real-time updates (zero polling)

## Scaling Considerations

### Horizontally Scalable Components
- IP Intelligence Aggregator (stateless)
- Network Reputation Scorer (Redis-backed)
- Chat Intelligence Engine (in-memory, reset per stream)
- Threat Correlation Engine (stateless)

### Stateful Components
- Behavioral Analyzer (stream-specific state, auto-cleared)
- Chat Intelligence (message windows cleared on stream end)

### Recommended Setup
- **Small**: Single instance with Redis + MongoDB
- **Medium**: 2-3 FastAPI instances + Redis cluster + MongoDB
- **Large**: 5+ FastAPI instances + Redis cluster + MongoDB sharded

## Monitoring & Alerts

### Key Metrics

```python
# Prometheus metrics
http_requests_total
http_request_duration_seconds
ai_assessments_total
ai_early_warnings_total
ai_inference_latency
threat_scores_by_stream
detected_attacks_total
```

### Alert Conditions

```python
# Alert on:
- Overall risk score >= 0.8 (CRITICAL)
- Multiple attack types detected simultaneously
- False positive rate > 5%
- API response latency > 1000ms
```

## Testing

### Unit Tests
```bash
pytest tests/test_threat_intel.py
pytest tests/test_behavioral.py
pytest tests/test_chat_intel.py
```

### Integration Tests
```bash
pytest tests/test_threat_correlation.py
pytest tests/test_ip_assessment.py
```

### Load Testing
```bash
# Simulate 1000 concurrent streams with threats
locust -f locustfile.py --users 1000 --spawn-rate 50
```

## Troubleshooting

### High False Positives
- Lower threat score thresholds
- Adjust pattern detection sensitivity
- Increase historical data window

### Slow IP Assessment
- Check Redis connectivity
- Verify API key rate limits
- Enable IP caching (TTL)
- Use batch assessment for multiple IPs

### WebSocket Disconnections
- Check WebSocket URL (wss vs ws)
- Verify CORS configuration
- Monitor network connectivity
- Implement client-side reconnection logic

## References

- IPInfo API: https://ipinfo.io/docs
- AbuseIPDB API: https://docs.abuseipdb.com/
- MaxMind GeoIP2: https://dev.maxmind.com/geoip
- Spamhaus: https://www.spamhaus.org/
- Onionoo API: https://onionoo.torproject.org/
