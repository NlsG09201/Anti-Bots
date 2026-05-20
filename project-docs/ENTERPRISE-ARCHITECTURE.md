# StreamShield Enterprise — Anti-Viewbotting Platform

**Version:** 2.0 · **Platforms:** Twitch (production), Kick & YouTube (integration layer)  
**Pattern:** Event-driven monolith with horizontal workers · **Stores:** PostgreSQL (Neon), Redis (streams/cache/rate-limit)

---

## 1. High-level architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │  CDN / WAF (Cloudflare) + Vercel (Next.js dashboard)     │
                    └───────────────────────────┬─────────────────────────────┘
                                                │ HTTPS / WSS
                    ┌───────────────────────────▼─────────────────────────────┐
                    │  API Gateway (FastAPI)                                   │
                    │  SecurityGateway → CSRF → Auth → REST + WebSocket        │
                    └───────┬───────────────────────────────┬─────────────────┘
                            │                               │
              ┌─────────────▼─────────────┐     ┌───────────▼──────────────┐
              │  Platform adapters         │     │  Event bus (Redis)      │
              │  Twitch · Kick · YouTube   │     │  Streams + Pub/Sub      │
              └─────────────┬─────────────┘     └───────────┬──────────────┘
                            │                               │
              ┌─────────────▼───────────────────────────────┴──────────────┐
              │  Detection plane                                                │
              │  Fingerprint · IP/ASN · Network policy · Viewbot · Anomaly AI   │
              └─────────────┬──────────────────────────────────────────────────┘
                            │
              ┌─────────────▼─────────────┐     ┌────────────────────────────┐
              │  PostgreSQL (OLTP)       │     │  Workers (arq / Celery)     │
              │  streams · sessions ·    │     │  pipeline · correlation   │
              │  attacks · audit         │     │  platform sync            │
              └──────────────────────────┘     └────────────────────────────┘
```

### Design principles (Backend Architect)

| Principle | Implementation |
|-----------|----------------|
| Defense in depth | Gateway rate limit → header validation → CSRF → JWT → per-stream RBAC |
| Horizontal scale | Stateless API; Redis consumer groups; partitioned event streams |
| Platform abstraction | `PlatformAdapter` registry; Twitch full path; Kick/YouTube ingest stubs |
| Observable | Prometheus counters on event bus; structured logs; SOC dashboard |
| Fail closed on auth | 401/403; rate limit with Bearer-aware buckets for dashboard |

---

## 2. Service decomposition

### 2.1 Ingest & platforms

| Service | Responsibility | Storage |
|---------|----------------|---------|
| **Platform registry** | OAuth, live status, chatters/viewers per platform | `streams`, encrypted tokens |
| **Widget ingest** | Browser fingerprint + join events | Redis stream → processor |
| **Webhook ingest** | Twitch EventSub | HMAC validation → bus |

### 2.2 Detection plane

| Layer | Signals | Output |
|-------|---------|--------|
| **Fingerprint** | webdriver, headless UA, canvas entropy | `risk_score`, device hash |
| **Network policy** | VPN, proxy, TOR, datacenter, blocked ASN/country | `network_risk`, `block_recommendation` |
| **Viewbot engine** | join velocity, IP clustering, chat silence | `AttackType.VIEWBOT` |
| **Anomaly intelligence** | Z-score baselines, IsolationForest on feature vectors | `anomaly_score`, `behavioral_flags` |
| **Correlation** | Cross-session graph, follow bursts | coordinated attack score |

### 2.3 Mitigation

| Action | Twitch | Kick | YouTube |
|--------|--------|------|---------|
| Local ban record | ✓ | ✓ | ✓ |
| Platform API ban | Helix moderation | Roadmap | Roadmap |
| Cloudflare block | Optional | Optional | Optional |

---

## 3. Data model (PostgreSQL — primary)

> **Note:** Production uses **PostgreSQL (Neon)**, not MongoDB. High-volume raw events can optionally archive to MongoDB Atlas for analytics; OLTP remains Postgres.

### Hot paths & indexes

See `backend/sql/enterprise_indexes.sql`.

| Table | Hot query | Index strategy |
|-------|-----------|----------------|
| `stream_events` | By `stream_id` + time | `(stream_id, created_at DESC)` |
| `viewer_sessions` | Active by stream | `(stream_id, status)` partial |
| `attacks` | Active by tenant/stream | `(stream_id, status)` |
| `fingerprints` | Hash lookup | UNIQUE `(fingerprint_hash)` |

### Redis key schema

See `backend/app/infrastructure/cache/redis_schema.py`.

| Prefix | TTL | Purpose |
|--------|-----|---------|
| `ss:rl:*` | 60s | Rate limiting |
| `ss:evt:{tenant}:{stream}` | — | Event stream (partitioned) |
| `ss:baseline:{stream}` | 1h | Anomaly rolling stats |
| `ss:ip:{ip}` | 15m | Threat intel cache |
| `ss:pub:tenant:{id}` | — | WebSocket fanout |

---

## 4. Event throughput (millions/day)

Target: **1M+ events/day** per cluster (~12 evt/s sustained, 100+ evt/s burst).

| Mechanism | Config |
|-----------|--------|
| Redis Streams | `MAXLEN ~` trimming; consumer groups per worker |
| Sharding | `event_stream_shard(tenant_id, stream_id)` → 16 logical streams |
| Batch ingest | `EVENT_INGEST_BATCH_SIZE=50` |
| Async processing | arq worker + optional inline consumer |
| API rate limit | Burst skipped for Bearer; route buckets grouped |

Scale-out: N API replicas + M workers; single Redis Cluster or Upstash; Postgres read replica for dashboards.

---

## 5. Security controls (Security Engineer)

| Control | Status |
|---------|--------|
| JWT access + HttpOnly refresh + CSRF on cookie mutations | ✓ |
| IP reputation (proxy/VPN/TOR/datacenter) | ✓ |
| **Network policy engine** | ✓ `network_policy.py` |
| Widget HMAC + replay window | Configurable |
| Automation header blocking | Gateway |
| Geo block list | `SECURITY_BLOCKED_COUNTRIES` |

---

## 6. AI / anomaly layer (AI Engineer)

| Component | Method |
|-----------|--------|
| `AnomalyIntelligenceService` | Rolling baselines + z-score + optional sklearn |
| `AIService` | OpenAI narrative for SOC alerts (optional) |
| Realtime viewbot | Sliding window + rules |

Feature vector (per stream, 60s window): joins/min, unique IPs, fingerprint collision rate, proxy ratio, chat ratio.

---

## 7. Frontend (SOC)

- **SOC Command Center** — metrics, attack map, timeline, alerts
- **Multi-platform** — channel cards show Twitch / Kick / YouTube badges
- **Deploy page** — env checklist for enterprise stack

---

## 8. Deployment (DevOps)

| Environment | Stack |
|-------------|--------|
| Local enterprise | `deploy/enterprise/docker-compose.enterprise.yml` |
| Production | Vercel (UI) + Render (API) + Neon + Upstash Redis |
| CI | `.github/workflows/ci.yml` |

---

## 9. Roadmap

1. **Kick** — OAuth + chat webhook → `KickAdapter.sync_viewers`
2. **YouTube** — Live Chat API polling → `YouTubeAdapter.sync_viewers`
3. **MongoDB archive** (optional) — TTL collections for raw events > 90 days
4. **Multi-region** — Redis Global + Postgres read replicas

---

## 10. File map (new enterprise modules)

```
backend/app/services/platforms/          # Platform adapters
backend/app/services/security/network_policy.py
backend/app/services/detection/anomaly_intelligence.py
backend/app/infrastructure/cache/redis_schema.py
backend/app/events/sharding.py
backend/sql/enterprise_indexes.sql
backend/app/api/v1/enterprise.py
deploy/enterprise/docker-compose.enterprise.yml
.github/workflows/ci.yml
```
