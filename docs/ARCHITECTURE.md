# StreamShield Architecture

## System Overview

StreamShield is an enterprise anti-bot security platform for live streamers on Twitch, Kick, and YouTube Live.

```mermaid
flowchart TB
    subgraph Clients
        FE[Next.js Dashboard]
        EXT[Platform Webhooks]
    end

    subgraph Edge
        NGINX[NGINX Reverse Proxy]
        CF[Cloudflare WAF]
    end

    subgraph API Layer
        API[FastAPI API]
        WS[WebSocket Manager]
    end

    subgraph Processing
        DET[Detection Engine]
        COR[Correlation Service]
        MIT[Mitigation Service]
        REP[Reputation Service]
    end

    subgraph Workers
        CW[Celery Workers]
        CB[Celery Beat]
    end

    subgraph Data
        PG[(PostgreSQL)]
        RD[(Redis)]
        RMQ[RabbitMQ]
    end

    subgraph External
        TW[Twitch EventSub]
        KI[Kick API]
        YT[YouTube Live API]
        TI[Threat Intel APIs]
        DC[Discord Webhooks]
    end

    FE --> NGINX --> API
    FE --> WS
    EXT --> API
    API --> DET
    API --> COR
    API --> MIT
    DET --> REP
    API --> PG
    API --> RD
    CW --> RMQ
    CW --> DET
    TW --> API
    KI --> API
    YT --> API
    REP --> TI
    MIT --> DC
```

## Event Flow

```mermaid
sequenceDiagram
    participant P as Platform
    participant API as FastAPI
    participant DET as Detection Engine
    participant COR as Correlation
    participant MIT as Mitigation
    participant WS as WebSocket
    participant DB as PostgreSQL

    P->>API: Webhook Event (follow/chat/view)
    API->>DET: Analyze fingerprint + IP
    API->>DB: Store StreamEvent
    DET-->>API: Risk Score + Evidence
    alt Risk >= 50
        API->>COR: Create Attack Record
        COR->>DB: Store Attack + Alert
        API->>WS: Broadcast Alert
        alt Risk >= 70
            API->>MIT: Progressive Mitigation
            MIT->>DB: Create Ban/Quarantine
        end
    end
```

## Detection Pipeline

```mermaid
flowchart LR
    E[Raw Event] --> FP[Fingerprint Analysis]
    E --> IP[IP Reputation]
    E --> BEH[Behavioral Analysis]
    FP --> SC[Score Aggregation]
    IP --> SC
    BEH --> SC
    SC --> ML[Isolation Forest ML]
    ML --> DEC{Score >= Threshold?}
    DEC -->|Yes| ATK[Create Attack]
    DEC -->|No| LOG[Log Event]
    ATK --> MIT[Mitigation Action]
```

## Multi-Tenant Model

- Each **Tenant** represents a streamer organization
- **Users** belong to tenants with RBAC roles
- **Streams** are linked to platforms (Twitch/Kick/YouTube)
- All security data is tenant-isolated

## Security Layers

| Layer | Implementation |
|-------|---------------|
| Transport | TLS 1.3, HSTS, secure WebSockets |
| Authentication | JWT + refresh tokens, token blacklist |
| Authorization | RBAC (5 roles) |
| Rate Limiting | Redis distributed rate limiter |
| Input Validation | Pydantic v2 strict schemas |
| Encryption | AES-256 Fernet for OAuth tokens |
| Headers | CSP, X-Frame-Options, nosniff |
| Audit | Immutable audit log table |

## Scalability Strategy

- **Horizontal**: API replicas behind NGINX, HPA in Kubernetes
- **Async**: Celery workers for detection/correlation
- **Cache**: Redis for rate limits, bans, IP reputation
- **Database**: Connection pooling, indexed queries, future partitioning by tenant_id
