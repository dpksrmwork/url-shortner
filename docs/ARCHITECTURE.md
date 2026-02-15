# URL Shortener - System Architecture

## Overview

High-performance URL shortening service with production-grade monitoring, caching, and observability.

**Tech Stack:**
- **API**: FastAPI (Python 3.12) + Uvicorn
- **Database**: Apache Cassandra 4.1
- **Cache**: Redis 7
- **API Gateway**: Kong 3.4
- **Monitoring**: Prometheus + Grafana
- **Deployment**: Docker Compose / Kubernetes

---

## System Architecture Diagram

```
                                    Internet
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │      Kong API Gateway        │
                        │  - Rate Limiting             │
                        │  - SSL Termination           │
                        │  - Metrics Collection        │
                        │  - Request Routing           │
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────┴───────────────┐
                        │                              │
                        ▼                              ▼
            ┌───────────────────────┐      ┌───────────────────────┐
            │   FastAPI Service     │      │   FastAPI Service     │
            │   (Stateless)         │      │   (Stateless)         │
            │                       │      │                       │
            │  - URL Shortening     │      │  - URL Shortening     │
            │  - URL Redirect       │      │  - URL Redirect       │
            │  - Analytics API      │      │  - Analytics API      │
            └───────┬───────────────┘      └───────┬───────────────┘
                    │                              │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
        ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
        │  Redis Cache     │  │  Cassandra   │  │   Prometheus     │
        │                  │  │   Cluster    │  │                  │
        │ - URL Cache      │  │              │  │ - Metrics Store  │
        │ - Dedup Cache    │  │ - urls       │  │ - Time Series DB │
        │ - Rate Limiting  │  │ - url_clicks │  │                  │
        │ - ID Generation  │  │ - url_dedup  │  └────────┬─────────┘
        └──────────────────┘  └──────────────┘           │
                                                          ▼
                                               ┌──────────────────┐
                                               │     Grafana      │
                                               │                  │
                                               │ - Dashboards     │
                                               │ - Visualization  │
                                               │ - Alerting       │
                                               └──────────────────┘
```

---

## Component Details

### 1. Kong API Gateway

**Purpose**: Entry point for all traffic, handles cross-cutting concerns

**Responsibilities:**
- SSL/TLS termination
- Rate limiting (per IP, per user)
- Request routing to backend services
- Metrics collection (Prometheus plugin)
- Request/response logging

**Configuration:**
- Port 80: HTTP proxy to FastAPI
- Port 8001: Admin API
- Database: PostgreSQL (for Kong config)
- Plugins: Prometheus, Rate Limiting

**Metrics Exposed:**
- `kong_http_status` - HTTP status codes
- `kong_latency` - Request/upstream/Kong latency
- `kong_bandwidth` - Request/response sizes
- `kong_datastore_reachable` - Database health

---

### 2. FastAPI Application

**Purpose**: Core business logic for URL shortening

**Endpoints:**

```python
POST   /shorten              # Create short URL
GET    /{short_code}         # Redirect to long URL
GET    /stats/{short_code}   # Get URL statistics
GET    /health               # Health check
```

**Architecture:**

```
app/
├── main.py                  # FastAPI app initialization
├── api/
│   └── endpoints.py         # Route handlers
├── core/
│   ├── config.py            # Configuration management
│   └── security.py          # Security utilities
├── db/
│   ├── cassandra.py         # Cassandra connection
│   └── redis.py             # Redis connection
├── middleware/
│   ├── rate_limit.py        # Rate limiting logic
│   └── security_headers.py  # Security headers
├── models/
│   └── schemas.py           # Pydantic models
└── services/
    └── url_service.py       # Business logic
```

**Key Features:**
- Async I/O for high concurrency
- Connection pooling (Cassandra, Redis)
- Request validation (Pydantic)
- Error handling & logging
- Health checks

---

### 3. Redis Cache

**Purpose**: High-speed cache layer and distributed utilities

**Data Structures:**

```redis
# URL Cache (String)
url:{short_code} → {long_url}
TTL: 3600s (1 hour)

# Deduplication Cache (String)
dedup:{sha256_hash} → {short_code}
TTL: 86400s (24 hours)

# Rate Limiter (Sorted Set)
ratelimit:{user_id}:create → {timestamp}:{request_id}
TTL: 60s (sliding window)

# ID Generator (Counter)
shortcode:counter → INCR
```

**Configuration:**
- Memory: 256MB
- Eviction: allkeys-lru
- Persistence: Disabled (cache only)
- Password protected

---

### 4. Cassandra Database

**Purpose**: Primary data store for URLs

**Schema:**

```cql
-- Main URL storage
CREATE TABLE urls (
    short_code TEXT PRIMARY KEY,
    long_url TEXT,
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    user_id TEXT
);

-- Click tracking
CREATE TABLE url_clicks (
    short_code TEXT PRIMARY KEY,
    click_count COUNTER
);

-- Deduplication index
CREATE TABLE url_dedup (
    url_hash TEXT PRIMARY KEY,
    short_code TEXT
);
```

**Configuration:**
- Replication Factor: 1 (dev), 3 (prod)
- Consistency Level: QUORUM (writes), ONE (reads)
- Compaction: LeveledCompactionStrategy
- Compression: LZ4

---

### 5. Prometheus

**Purpose**: Metrics collection and storage

**Scrape Targets:**
- Kong metrics: `http://kong:8001/metrics`
- FastAPI metrics: `http://api:8000/metrics` (if enabled)

**Configuration:**
```yaml
scrape_configs:
  - job_name: 'kong'
    static_configs:
      - targets: ['kong:8001']
    scrape_interval: 15s
```

**Retention:** 15 days

---

### 6. Grafana

**Purpose**: Metrics visualization and dashboards

**Dashboards:**
- Total requests per second
- Latency (p50, p95, p99)
- HTTP status codes
- Cache hit rate
- Error rate

**Data Source:** Prometheus at `http://prometheus:9090`

**Access:** `http://localhost:3000` (admin/password from env)

---

## Data Flows

### Flow 1: URL Creation

```
Client → Kong → FastAPI → Redis/Cassandra

1. Client sends POST /shorten with long_url
2. Kong validates rate limit, forwards to FastAPI
3. FastAPI validates URL format
4. Check Redis dedup cache for existing short_code
5. If not found, check Cassandra url_dedup table
6. Generate new short_code (Redis INCR + Base62)
7. Insert into Cassandra (urls, url_dedup tables)
8. Cache in Redis (url:{code}, dedup:{hash})
9. Return short_url to client

Latency: ~50-200ms
```

### Flow 2: URL Redirect (Hot Path)

```
Client → Kong → FastAPI → Redis (95%) or Cassandra (5%)

1. Client sends GET /{short_code}
2. Kong forwards to FastAPI
3. FastAPI checks Redis cache (url:{short_code})
4. If HIT (95%): Return 301 redirect immediately
5. If MISS (5%): Query Cassandra urls table
6. Cache result in Redis
7. Increment click counter (async)
8. Return 301 redirect to client

Latency: ~10-50ms (cache hit), ~50-150ms (cache miss)
```

### Flow 3: Analytics Query

```
Client → Kong → FastAPI → Cassandra

1. Client sends GET /stats/{short_code}
2. Kong forwards to FastAPI
3. FastAPI queries Cassandra:
   - urls table (metadata)
   - url_clicks table (click count)
4. Return aggregated stats

Latency: ~50-100ms
```

---

## Scaling Strategy

### Horizontal Scaling

**API Servers:**
- Stateless design allows unlimited horizontal scaling
- Deploy behind Kong load balancer
- Auto-scale based on CPU/memory/request rate

**Cassandra:**
- Add nodes to cluster for more capacity
- Rebalance data across nodes
- Linear scalability

**Redis:**
- Use Redis Cluster for sharding
- 6 nodes: 3 masters + 3 replicas
- Automatic failover

### Vertical Scaling

**API Servers:**
- Increase CPU/memory for higher concurrency
- Tune Uvicorn workers (2 × CPU cores)

**Cassandra:**
- More RAM = larger cache = faster reads
- NVMe SSDs for lower latency

---

## Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| **Write Latency (p99)** | <500ms | ~200ms |
| **Read Latency (p99)** | <100ms | ~50ms |
| **Cache Hit Rate** | >90% | ~95% |
| **Availability** | 99.9% | - |
| **Write TPS** | 2,000 | - |
| **Read TPS** | 200,000 | - |

---

## Security Features

### Application Security
- Input validation (URL format, length)
- Blocklist for malicious domains
- Rate limiting (per IP, per user)
- HTTPS/TLS encryption
- Security headers (HSTS, CSP, X-Frame-Options)

### Infrastructure Security
- Network isolation (Docker networks)
- Secret management (Kubernetes Secrets)
- Database authentication (passwords)
- Redis password protection
- Kong admin API access control

---

## Monitoring & Observability

### Metrics (Prometheus + Grafana)
- Request rate (requests/sec)
- Latency percentiles (p50, p95, p99)
- Error rate (4xx, 5xx)
- Cache hit rate
- Database latency
- Resource utilization (CPU, memory, disk)

### Logging
- Structured JSON logs
- Request/response logging
- Error tracking
- Audit logs

### Alerting
- High error rate (>1%)
- High latency (p99 >500ms)
- Low cache hit rate (<80%)
- Database unavailability
- Disk space low (<20%)

---

## Deployment

### Docker Compose (Development)

```bash
make cassandra-up      # Start Cassandra
make cassandra-init    # Initialize schema
make run               # Start all services
```

**Services:**
- Cassandra: `localhost:9042`
- Redis: `localhost:6379`
- Kong: `localhost:80` (proxy), `localhost:8001` (admin)
- API: `localhost:8000`
- Prometheus: `localhost:9090`
- Grafana: `localhost:3000`

### Kubernetes (Production)

```bash
./scripts/k8s-deploy.sh    # Deploy to K8s
./scripts/kong-setup.sh    # Configure Kong
```

**Resources:**
- Namespace: `url-shortener`
- Secrets: `url-shortener-secrets`
- Services: Cassandra, Redis, Kong, API, Prometheus, Grafana
- Ingress: Kong (SSL termination)

---

## Capacity Planning

### Storage Requirements

**Cassandra:**
- 1 URL = ~500 bytes (metadata + indexes)
- 1B URLs = 500GB
- 3 years × 1B URLs/month = 18TB
- With RF=3: 54TB total

**Redis:**
- 10M hot URLs × 200 bytes = 2GB
- Overhead + other data = 4GB per instance
- 6 nodes × 4GB = 24GB total

### Compute Requirements

**For 200K TPS (read), 2K TPS (write):**

| Component | vCPU | RAM | Disk | Count |
|-----------|------|-----|------|-------|
| API | 4 | 8GB | 20GB | 10 |
| Cassandra | 8 | 32GB | 2TB | 6 |
| Redis | 2 | 8GB | 20GB | 6 |
| Kong | 4 | 8GB | 20GB | 2 |
| Prometheus | 4 | 16GB | 500GB | 1 |
| Grafana | 2 | 4GB | 20GB | 1 |

---

## Disaster Recovery

### Backup Strategy
- Cassandra: Daily snapshots to S3
- Redis: Not backed up (cache only)
- Prometheus: 15-day retention
- Grafana: Dashboard configs in Git

### Recovery Procedures
- Cassandra node failure: Automatic repair
- Redis failure: Rebuild cache from Cassandra
- Full datacenter loss: Restore from S3 backup
- RTO: 4 hours, RPO: 24 hours

---

## Future Enhancements

1. **Custom Domains**: Allow users to use their own domains
2. **QR Codes**: Generate QR codes for short URLs
3. **Link Expiration**: Auto-expire URLs after TTL
4. **Analytics Dashboard**: Real-time click analytics
5. **A/B Testing**: Multiple destinations per short code
6. **Geo-Routing**: Route based on user location
7. **API Authentication**: OAuth2/JWT for API access
8. **Webhooks**: Notify on URL events
9. **CDN Integration**: CloudFlare for edge caching
10. **Multi-Region**: Deploy across multiple regions

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Cassandra Documentation](https://cassandra.apache.org/doc/)
- [Redis Documentation](https://redis.io/docs/)
- [Kong Documentation](https://docs.konghq.com/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
