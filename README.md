# 🔗 URL Shortener

A production-grade URL shortening service built as a **system design exercise**, demonstrating how to architect a high-throughput, low-latency web service with real-world infrastructure components.

> **Why this project?** URL shorteners appear simple — take a long URL, return a short one. But building one that handles millions of redirects, deduplicates URLs, tracks analytics, enforces rate limits, and runs behind an API gateway with HTTPS touches nearly every backend engineering concern: hashing, caching, database modelling, security, container orchestration, and observability.

---

## Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Quick Start (Docker Compose)](#-quick-start-docker-compose)
- [API Reference](#-api-reference)
- [Database Schema](#-database-schema)
- [Security](#-security)
- [Kong API Gateway](#-kong-api-gateway)
- [Monitoring & Observability](#-monitoring--observability)
- [Kubernetes Deployment](#-kubernetes-deployment)
- [Testing](#-testing)
- [Configuration](#-configuration)
- [Capacity Planning](#-capacity-planning)
- [Project Structure](#-project-structure)
- [Makefile Commands](#-makefile-commands)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 📐 Architecture

### High-Level Overview

```
                              Internet
                                 │
                         ┌───────┴────────┐
                         │  Kong Gateway  │  ← HTTPS termination, rate limiting,
                         │  (port 443/80) │    load balancing, metrics
                         └───────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
          ┌──────────────────┐     ┌──────────────────┐
          │  FastAPI Service │     │  FastAPI Service  │  ← Stateless, horizontally
          │  (replica 1)     │     │  (replica N)      │    scalable workers
          └────────┬─────────┘     └────────┬──────────┘
                   │                        │
          ┌────────┴────────────────────────┴──────────┐
          │                                            │
          ▼                    ▼                       ▼
  ┌──────────────┐    ┌──────────────┐     ┌────────────────────┐
  │  Redis 7     │    │ Cassandra 4.1│     │ Prometheus+Grafana │
  │              │    │              │     │                    │
  │ • URL cache  │    │ • urls       │     │ • Request rates    │
  │ • Dedup cache│    │ • url_clicks │     │ • Latency (p99)    │
  │ • Rate limits│    │ • url_dedup  │     │ • Error rates      │
  └──────────────┘    └──────────────┘     └────────────────────┘
```

### How a Request Flows

#### Creating a short URL (`POST /shorten`)

```
Client ──→ Kong (rate limit check) ──→ FastAPI ──→ Redis dedup cache
                                                        │
                                                hit? ◄──┘
                                               ╱    ╲
                                            yes      no
                                             │        │
                                     return existing  │
                                     short code   ┌───┘
                                                  ▼
                                          Cassandra url_dedup
                                                  │
                                           hit? ◄─┘
                                          ╱    ╲
                                       yes      no
                                        │        │
                                return existing  Generate new code
                                short code   (SHA-256 + secrets.token_bytes)
                                                  │
                                                  ▼
                                          Write to Cassandra (urls + url_dedup)
                                          Cache in Redis
                                                  │
                                                  ▼
                                          Return short_url to client
```

1. Request arrives at **Kong**, which checks the rate limit and forwards to an API worker.
2. **FastAPI** validates the URL (scheme, blocklist, length) and sanitises inputs.
3. A SHA-256 hash of the URL is checked against the **Redis** dedup cache, then **Cassandra** `url_dedup` table — if the URL was shortened before, the existing short code is returned immediately (deduplication).
4. If it's new, a short code is generated using SHA-256 + `secrets.token_bytes` (collision-resistant, non-sequential).
5. The mapping is written to Cassandra (`urls`, `url_dedup`) and cached in Redis.
6. The short URL is returned to the client.

#### Redirecting (`GET /{short_code}`) — The Hot Path

```
Client ──→ Kong ──→ FastAPI ──→ Redis cache
                                    │
                             hit? ◄─┘ (95% of requests)
                            ╱    ╲
                         yes      no (5%)
                          │        │
                  301 Redirect   Query Cassandra
                  (~5ms)         Cache result in Redis
                                 301 Redirect (~50ms)
                                      │
                                      ▼
                              Increment click counter (async)
```

1. Kong forwards the request to an API worker.
2. FastAPI checks **Redis** first (~95% cache hit) → returns a `301 Permanent Redirect` in **~5 ms**.
3. On cache miss, Cassandra is queried, the result is cached, and the redirect is returned in **~50 ms**.
4. The click counter is incremented asynchronously (doesn't block the response).

#### Analytics Query (`GET /stats/{short_code}`)

```
Client ──→ Kong ──→ FastAPI ──→ Cassandra (urls + url_clicks tables)
                                    │
                                    ▼
                            Return aggregated stats (~50-100ms)
```

---

## ✨ Features

| Category | Details |
|----------|---------|
| **Core** | URL shortening, 301 redirects, custom aliases (3-30 chars), configurable TTL (default 3 years), URL deduplication via SHA-256 hashing |
| **Performance** | Redis caching (~5 ms redirect latency), async click tracking, connection pooling |
| **Security** | HTTPS/TLS via Kong, HSTS, CSP headers, input validation, URL blocklist, path traversal prevention, non-root containers |
| **Rate Limiting** | Dual-layer: Kong (gateway) + FastAPI middleware (app-level), sliding window algorithm, Redis-backed |
| **Analytics** | Click counting per URL, stats API endpoint |
| **Observability** | Prometheus metrics via Kong plugin, Grafana dashboards with pre-built panels, structured logging |
| **Deployment** | Docker Compose (dev), Kubernetes manifests (prod) with HPA auto-scaling (3-10 replicas) |

---

## 🛠 Tech Stack

| Component | Technology | Why This Choice |
|-----------|-----------|-----------------|
| **API** | FastAPI + Uvicorn | Async Python with auto-generated OpenAPI docs, high concurrency via `asyncio` |
| **Database** | Apache Cassandra 4.1 | Optimised for write-heavy workloads, linear horizontal scalability, tunable consistency |
| **Cache** | Redis 7 | Sub-millisecond reads, native TTL, sorted sets for sliding-window rate limiting |
| **Gateway** | Kong 3.4 | Plugin ecosystem (rate limiting, Prometheus, CORS, caching), HTTPS termination, load balancing |
| **Monitoring** | Prometheus + Grafana | Industry-standard metrics pipeline, pre-built dashboards, alerting |
| **Container** | Docker + Docker Compose | Consistent local development, single-command startup |
| **Orchestration** | Kubernetes | Production deployment with auto-scaling, self-healing, rolling updates |

---

## 🚀 Quick Start (Docker Compose)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) (v2+)
- `curl` (for testing)
- `openssl` (for SSL cert generation)

### Step 1: Clone & Configure

```bash
git clone <your-repo-url> url-shortner
cd url-shortner

# Create environment file from template
cp .env.example .env
# Edit .env and set your own passwords (or keep defaults for local dev)
```

### Step 2: Generate SSL Certificate

```bash
make ssl-setup
# or manually:
mkdir -p ssl/certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ssl/certs/key.pem -out ssl/certs/cert.pem \
  -days 365 -subj "/CN=localhost"
```

### Step 3: Start All Services

```bash
# Build the API image
make docker-build

# Start everything: Cassandra, Redis, Kong, API, Prometheus, Grafana
make docker-up          # Waits ~45s for Cassandra to become healthy

# Configure Kong routes and plugins
make kong-setup
```

### Step 4: Verify Everything is Running

```bash
# Health check via HTTPS (through Kong)
curl -sk https://localhost/health
# → {"status":"healthy","cassandra":"connected","redis":"connected"}

# Health check via HTTP
curl -s http://localhost/health
# → same response

# Check all containers
docker compose ps
```

### Step 5: Try It Out

```bash
# Shorten a URL
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/fastapi/fastapi"}'
# → {"short_code":"aBcDeFgH","short_url":"https://localhost/aBcDeFgH","long_url":"https://github.com/fastapi/fastapi"}

# Follow the redirect
curl -skL https://localhost/aBcDeFgH
# → redirects to https://github.com/fastapi/fastapi

# With a custom alias
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "custom_alias": "ex", "ttl_days": 30}'
# → {"short_code":"ex","short_url":"https://localhost/ex","long_url":"https://example.com"}

# Check stats
curl -sk https://localhost/stats/ex
# → {"short_code":"ex","long_url":"https://example.com","clicks":0,"expires_at":"..."}
```

### Stopping

```bash
make docker-down        # Stop and remove all containers
```

---

## 📖 API Reference

All endpoints are accessible through the Kong gateway at `https://localhost` (HTTPS) or `http://localhost` (HTTP).

Interactive Swagger UI available at: **`https://localhost/docs`**

### `POST /shorten` — Create a Short URL

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | — | The URL to shorten (must be `http://` or `https://`, max 2048 chars) |
| `custom_alias` | string | ❌ | auto-generated | Custom short code (3–30 chars, alphanumeric + `-_`, must start with letter/number) |
| `user_id` | string | ❌ | — | Optional user identifier for tracking |
| `ttl_days` | integer | ❌ | 1095 (3 years) | Expiration in days |

**Request:**
```bash
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/very/long/path", "custom_alias": "mylink", "ttl_days": 365}'
```

**Response** (`200 OK`):
```json
{
  "short_code": "mylink",
  "short_url": "https://localhost/mylink",
  "long_url": "https://example.com/very/long/path"
}
```

**Error Responses:**

| Code | Reason |
|------|--------|
| `400` | Invalid URL format, blocked domain, or reserved alias |
| `409` | Custom alias already exists |
| `422` | Validation error (malicious scheme, bad characters) |
| `429` | Rate limit exceeded |

### `GET /{short_code}` — Redirect to Original URL

Returns a `301 Permanent Redirect` to the original URL. Increments the click counter asynchronously.

```bash
curl -skL https://localhost/mylink    # follows redirect
curl -sk  https://localhost/mylink    # shows 301 headers only
```

| Code | Reason |
|------|--------|
| `301` | Redirect to original URL |
| `404` | Short code not found |
| `410` | URL has expired |

### `GET /stats/{short_code}` — Get URL Analytics

```bash
curl -sk https://localhost/stats/mylink
```

**Response** (`200 OK`):
```json
{
  "short_code": "mylink",
  "long_url": "https://example.com/very/long/path",
  "clicks": 42,
  "expires_at": "2027-02-24T15:30:00"
}
```

### `GET /health` — Health Check

Used by Docker and Kubernetes probes.

```bash
curl -sk https://localhost/health
```

**Response** (`200 OK`):
```json
{
  "status": "healthy",
  "cassandra": "connected",
  "redis": "connected"
}
```

### `GET /docs` — Swagger UI

Open in browser: `https://localhost/docs`

### `GET /redoc` — ReDoc API Docs

Open in browser: `https://localhost/redoc`

---

## 🗄 Database Schema

The Cassandra schema (defined in `cassandra/init/01-schema.cql`) uses five tables, each optimised for a specific access pattern:

### Core Tables

```
┌──────────────────────────────────────┐    ┌──────────────────────────────────┐
│              urls                    │    │          url_clicks              │
│  (main URL storage)                  │    │  (click counters)                │
│──────────────────────────────────────│    │──────────────────────────────────│
│  short_code  TEXT       PRIMARY KEY  │    │  short_code  TEXT  PRIMARY KEY   │
│  long_url    TEXT                    │    │  click_count COUNTER             │
│  created_at  TIMESTAMP              │    └──────────────────────────────────┘
│  expires_at  TIMESTAMP              │
│  user_id     TEXT                    │    ┌──────────────────────────────────┐
│──────────────────────────────────────│    │          url_dedup               │
│  Compaction: LeveledCompaction       │    │  (deduplication index)            │
│  Default TTL: 3 years (94608000s)   │    │──────────────────────────────────│
│  GC Grace: 10 days                  │    │  url_hash    TEXT  PRIMARY KEY   │
└──────────────────────────────────────┘    │  short_code  TEXT                │
                                            │  created_at  TIMESTAMP           │
                                            └──────────────────────────────────┘
```

### User Tables

```
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│            users                 │    │          user_stats              │
│  (user profiles)                  │    │  (user URL counters)             │
│──────────────────────────────────│    │──────────────────────────────────│
│  user_id     TEXT  PRIMARY KEY   │    │  user_id    TEXT  PRIMARY KEY    │
│  email       TEXT                │    │  url_count  COUNTER              │
│  created_at  TIMESTAMP           │    └──────────────────────────────────┘
└──────────────────────────────────┘

Secondary Index: urls_by_user ON urls(user_id)
```

### Why Cassandra?

The read:write ratio is **100:1** at scale, but the write volume is still ~400 TPS (peak 2K). Cassandra is optimised for **high write throughput** with tunable consistency and **linear horizontal scalability** — adding nodes increases capacity without architectural changes.

### Why Separate Tables?

Cassandra doesn't support joins or efficient secondary indexes at scale. Instead, each table is a "materialised view" of the data, pre-shaped for its query pattern:

| Table | Query Pattern | Why Separate? |
|-------|--------------|---------------|
| `urls` | Lookup by `short_code` | Primary redirect path — must be fast |
| `url_clicks` | Increment by `short_code` | Cassandra requires counter columns in dedicated tables |
| `url_dedup` | Lookup by `url_hash` | Different partition key (hash vs code) — can't be in same table efficiently |
| `users` | Lookup by `user_id` | Different entity, different access pattern |
| `user_stats` | Counter by `user_id` | Counter columns require dedicated table |

### CQL Schema

```sql
CREATE KEYSPACE IF NOT EXISTS url_shortener
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1        -- Use 3 in production
};

CREATE TABLE urls (
  short_code text PRIMARY KEY,
  long_url text,
  created_at timestamp,
  expires_at timestamp,
  user_id text
) WITH compaction = {'class': 'LeveledCompactionStrategy'}
  AND gc_grace_seconds = 864000
  AND default_time_to_live = 94608000;  -- 3 years

CREATE TABLE url_clicks (
  short_code text PRIMARY KEY,
  click_count counter
);

CREATE TABLE url_dedup (
  url_hash text PRIMARY KEY,
  short_code text,
  created_at timestamp
) WITH compaction = {'class': 'LeveledCompactionStrategy'};
```

---

## 🔒 Security

### Defence in Depth (4 Layers)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: Kong Gateway                                                │
│   • HTTPS/TLS termination (TLS 1.2/1.3)                            │
│   • Gateway-level rate limiting (100/min, 10K/hr)                   │
│   • CORS policy                                                      │
│   • Proxy caching                                                    │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 2: FastAPI Middleware                                           │
│   • App-level rate limiting (sliding window, Redis-backed)           │
│   • Security headers (HSTS, CSP, X-Frame-Options, etc.)             │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 3: Input Validation                                            │
│   • URL scheme whitelist (http/https only)                           │
│   • Blocked patterns: javascript:, data:, vbscript:, file:          │
│   • Suspicious TLD blocking (.tk, .ml, .ga, .cf, .gq)              │
│   • IP-based URL blocking                                            │
│   • Domain blocklist (config/blocklist.txt)                          │
│   • Alias: alphanumeric + hyphen/underscore only                    │
│   • Reserved word blocking (admin, health, stats, etc.)             │
│   • Path traversal prevention (../, /, \)                           │
│   • URL length limit (2048 chars)                                    │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 4: Container Security                                          │
│   • Non-root user (appuser:appgroup)                                │
│   • Minimal base image (python:3.12-slim)                           │
│   • No shell access in production                                    │
│   • Health check built into image                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Security Headers (Every Response)

| Header | Value | Purpose |
|--------|-------|---------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | Force HTTPS for 1 year |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME-type sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Enable browser XSS filter |
| `Content-Security-Policy` | `default-src 'self'; ...` | Prevent XSS and injection |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer leakage |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | Disable unnecessary browser APIs |

### Rate Limiting

Two independent rate-limiting layers work together:

**Kong Gateway (Layer 1):**

| Scope | Limit |
|-------|-------|
| All endpoints | 100 req/min, 10,000 req/hr per IP |

**FastAPI Middleware (Layer 2):**

| Endpoint | Limit | Window | Algorithm |
|----------|-------|--------|-----------|
| `POST /shorten` | 100 req | 60s | Sliding window (Redis sorted set) |
| `GET /{code}` | 1,000 req | 60s | Sliding window |
| `GET /stats/*` | 200 req | 60s | Sliding window |
| Default | 500 req | 60s | Sliding window |

Responses include rate-limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 42
Retry-After: 60          ← only on 429 responses
```

### Short Code Generation

Short codes are generated using a **collision-resistant, non-sequential** algorithm:

```
SHA-256(long_url) + secrets.token_bytes(2) → Base64 → 8-char code
```

- **Non-sequential**: prevents enumeration attacks (attackers can't guess `abc124` from `abc123`)
- **Collision detection**: if a collision occurs, regenerate with fresh random bytes
- **Deduplication**: same URL always returns the same short code (via hash lookup)

### Secrets Management

| Secret | Storage | Committed to Git? |
|--------|---------|-------------------|
| Database passwords | `.env` file | ❌ No (`.gitignore`) |
| SSL certificates | `ssl/certs/` | ❌ No (`.gitignore`) |
| K8s secrets | `k8s/00-secrets.yaml` | ❌ No (`.gitignore`, only `.example` tracked) |
| API source code | `app/` | ✅ Yes (no secrets in code) |

### Security Testing

```bash
# Rate limiting (should get 429 after ~100 requests)
for i in $(seq 1 150); do
  curl -sk -o /dev/null -w "%{http_code} " -X POST https://localhost/shorten \
    -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
done

# Reserved word blocking → 400
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","custom_alias":"admin"}'

# Path traversal → 422
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","custom_alias":"../etc"}'

# Malicious URL scheme → 422
curl -sk -X POST https://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"javascript:alert(1)"}'
```

---

## 🌐 Kong API Gateway

Kong sits in front of all API instances and handles cross-cutting concerns.

### What Kong Does

| Feature | Configuration | Details |
|---------|--------------|---------|
| **HTTPS Termination** | Self-signed cert, TLS 1.2/1.3 | Clients connect via HTTPS; backend uses plain HTTP |
| **Load Balancing** | Upstream `url-shortener-upstream` | Round-robin across API replicas |
| **Rate Limiting** | `rate-limiting` plugin | 100/min, 10K/hr per IP |
| **Proxy Caching** | `proxy-cache` plugin | 5-min memory cache for GET requests |
| **CORS** | `cors` plugin | Cross-origin requests with configurable origins |
| **Metrics** | `prometheus` plugin | Exposes `/metrics` on admin port |

### Kong Routes

| Route | Path | Methods | Purpose |
|-------|------|---------|---------|
| `shorten-route` | `/shorten` | `POST` | Create short URLs |
| `stats-route` | `/stats` | `GET` | URL analytics |
| `health-route` | `/health` | `GET` | Health checks |
| `docs-route` | `/docs` | `GET` | Swagger UI |
| `openapi-route` | `/openapi.json` | `GET` | OpenAPI spec |
| `redirect-route` | `/` | All | Catch-all for short code redirects |

### Kong Admin API

```bash
# List all services
curl -s http://localhost:8001/services | python3 -m json.tool

# List all routes
curl -s http://localhost:8001/routes | python3 -m json.tool

# List all plugins
curl -s http://localhost:8001/plugins | python3 -m json.tool

# Check upstream health
curl -s http://localhost:8001/upstreams/url-shortener-upstream/health | python3 -m json.tool

# View Prometheus metrics
curl -s http://localhost:8001/metrics
```

### Verifying Traffic Goes Through Kong

Look for these headers in the response:

```
Via: kong/3.4.2                    ← confirms Kong proxied the request
X-Kong-Upstream-Latency: 2        ← time to reach FastAPI (ms)
X-Kong-Proxy-Latency: 1           ← time Kong spent processing (ms)
RateLimit-Remaining: 95           ← Kong rate-limit plugin
```

```bash
# Quick check
curl -sk -D - -o /dev/null https://localhost/health 2>/dev/null | grep -i kong
```

---

## 📊 Monitoring & Observability

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | `http://localhost:3000` | admin / (password from `.env`) |
| **Prometheus** | `http://localhost:9090` | — |
| **Kong Metrics** | `http://localhost:8001/metrics` | — |

### Metrics Pipeline

```
Kong ──(prometheus plugin)──→ Prometheus ──(datasource)──→ Grafana
  │                              │                            │
  ▼                              ▼                            ▼
/metrics endpoint         Scrapes every 15s            Dashboards & Alerts
```

### Kong Metrics (via Prometheus Plugin)

| Metric | Description |
|--------|-------------|
| `kong_http_requests_total` | Total request count by service, route, status code |
| `kong_request_latency_ms_bucket` | Request latency histogram (includes Kong overhead) |
| `kong_upstream_latency_ms_bucket` | Upstream (FastAPI) latency histogram |
| `kong_bandwidth_bytes` | Request and response sizes |
| `kong_datastore_reachable` | Kong's database connectivity (1 = healthy) |

### Pre-Built Grafana Dashboard

A dashboard JSON is included at `monitoring/grafana-dashboard.json`. To import:

1. Open Grafana at `http://localhost:3000`
2. Login (admin / password from `.env`)
3. Go to **Dashboards → Import**
4. Upload `monitoring/grafana-dashboard.json`
5. Select `Prometheus` as the data source
6. Click **Import**

**Dashboard Panels:**
- Requests per second (by status code)
- Latency percentiles (p50, p95, p99)
- HTTP status code distribution (2xx, 4xx, 5xx)
- Error rate (%)
- Bandwidth (ingress/egress)

### Prometheus Configuration

The scrape config is at `monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'kong'
    static_configs:
      - targets: ['kong:8001']
    metrics_path: '/metrics'
```

### Useful PromQL Queries

```promql
# Request rate (last 5 min)
rate(kong_http_requests_total[5m])

# p99 latency
histogram_quantile(0.99, rate(kong_request_latency_ms_bucket[5m]))

# Error rate (5xx)
rate(kong_http_requests_total{code=~"5.."}[5m]) / rate(kong_http_requests_total[5m])

# Requests by route
sum by (route) (rate(kong_http_requests_total[5m]))
```

---

## ☸️ Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (minikube, kind, or cloud provider)
- `kubectl` installed and configured
- Docker (for building images)

```bash
kubectl version --client
kubectl cluster-info
```

### Step-by-Step Deployment

#### 1. Create Namespace

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl get namespaces | grep url-shortener
```

#### 2. Create Secrets

```bash
# Option A: kubectl (recommended for production)
kubectl create secret generic url-shortener-secrets \
  --namespace=url-shortener \
  --from-literal=kong-pg-password=YOUR_SECURE_PASSWORD \
  --from-literal=grafana-admin-password=YOUR_SECURE_PASSWORD \
  --from-literal=redis-password=YOUR_SECURE_PASSWORD

# Option B: YAML file (for dev only)
cp k8s/00-secrets.yaml.example k8s/00-secrets.yaml
# Edit with real passwords, then:
kubectl apply -f k8s/00-secrets.yaml
```

#### 3. Deploy Databases

```bash
# Cassandra (takes 2-3 min to become ready)
kubectl apply -f k8s/01-cassandra.yaml
kubectl get pods -n url-shortener -w   # wait for cassandra-0 = 1/1 Running

# Kong Database (PostgreSQL)
kubectl apply -f k8s/02-kong-database.yaml
kubectl get pods -n url-shortener -l app=kong-database -w
```

#### 4. Initialize Cassandra Schema

```bash
kubectl exec -n url-shortener cassandra-0 -- cqlsh -f /schema/01-schema.cql

# Verify
kubectl exec -n url-shortener cassandra-0 -- cqlsh -e "DESCRIBE KEYSPACE url_shortener;"
```

#### 5. Deploy Kong

```bash
kubectl apply -f k8s/03-kong.yaml
# This runs migrations and starts the gateway
kubectl get pods -n url-shortener -l app=kong -w
```

#### 6. Deploy Redis

```bash
kubectl apply -f k8s/07-redis.yaml
kubectl get pods -n url-shortener -l app=redis -w
```

#### 7. Build & Deploy API

```bash
# For Minikube
eval $(minikube docker-env)
docker build -t url-shortener-api:latest .

# Deploy
kubectl apply -f k8s/04-api.yaml
kubectl get pods -n url-shortener -l app=url-shortener-api -w
```

#### 8. Deploy Monitoring

```bash
kubectl apply -f k8s/05-prometheus.yaml
kubectl apply -f k8s/06-grafana.yaml
```

#### 9. Configure Kong Routes

```bash
# Port-forward Kong admin
kubectl port-forward -n url-shortener svc/kong 8001:8001 &

# Run setup script
./scripts/kong-setup.sh
```

#### 10. Set Up HTTPS (Optional)

```bash
./scripts/k8s-ssl-setup.sh
```

### Accessing Services (K8s)

```bash
# Kong Proxy (API)
kubectl port-forward -n url-shortener svc/kong 8000:80
# → http://localhost:8000

# Grafana
kubectl port-forward -n url-shortener svc/grafana 3000:3000
# → http://localhost:3000

# Prometheus
kubectl port-forward -n url-shortener svc/prometheus 9090:9090
# → http://localhost:9090
```

### Automated Deployment

```bash
# Deploy everything in one command
./scripts/k8s-deploy.sh

# Access helper
./scripts/k8s-access.sh

# Monitor
./scripts/k8s-monitor.sh
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment api -n url-shortener --replicas=5

# Auto-scaling is configured via HPA (3-10 replicas, CPU target 70%)
kubectl get hpa -n url-shortener
```

### Rolling Updates

```bash
./scripts/k8s-update.sh
# Builds a new image, pushes it, and performs a rolling update
```

### Cleanup

```bash
# Remove everything
kubectl delete namespace url-shortener

# Or remove specific components
kubectl delete -f k8s/04-api.yaml
kubectl delete -f k8s/03-kong.yaml
# etc.
```

### K8s Verification Checklist

```bash
kubectl get pods -n url-shortener          # All pods Running?
kubectl get svc -n url-shortener           # All services created?
kubectl get secrets -n url-shortener       # Secrets exist?
kubectl get pvc -n url-shortener           # Persistent volumes bound?
kubectl get hpa -n url-shortener           # Auto-scaler active?
kubectl get events -n url-shortener --sort-by='.lastTimestamp'  # Recent events?
```

### Production Considerations

1. **Secrets management** — use Vault or AWS Secrets Manager instead of K8s Secrets
2. **Resource limits** — set CPU/memory requests and limits on all pods
3. **Persistent volumes** — use a fast StorageClass (SSD) for Cassandra
4. **Ingress** — use a proper Ingress controller instead of port-forwarding
5. **TLS** — use cert-manager with Let's Encrypt for auto-renewed certs
6. **Network policies** — restrict pod-to-pod communication
7. **Pod security** — enable `runAsNonRoot`, `readOnlyRootFilesystem`, drop all capabilities
8. **Backup** — regular Cassandra snapshots to S3
9. **Private registry** — use a private container registry for images
10. **Monitoring alerts** — configure Grafana alerts for error rate, latency, disk space

---

## 🧪 Testing

### Integration Tests

```bash
bash tests/test.sh
```

This script creates URLs, follows redirects, checks stats, and validates error handling.

### Latency Benchmarking

```bash
# Shell-based (uses curl)
bash tests/latency-test.sh

# Python-based (more detailed — p50, p95, p99 percentiles)
python tests/latency_test.py
```

### Manual Testing with Postman

Import the collection and environment into [Postman](https://www.postman.com/):

1. Import `assets/postman-collection.json`
2. Import `assets/postman-environment.json`
3. Select the "URL Shortener" environment
4. Run the collection

See `assets/POSTMAN.md` for detailed usage.

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `CASSANDRA_HOST` | `localhost` | Cassandra hostname |
| `CASSANDRA_PORT` | `9042` | Cassandra CQL port |
| `CASSANDRA_KEYSPACE` | `url_shortener` | Keyspace name |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | — | Redis authentication password |
| `KONG_PG_PASSWORD` | — | Kong PostgreSQL password |
| `GF_SECURITY_ADMIN_PASSWORD` | — | Grafana admin password |
| `BASE_URL` | `https://localhost` | Base URL for generated short links |

### Redis Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Max memory | 256 MB | Sufficient for dev; increase in production |
| Eviction policy | `allkeys-lru` | Evict least-recently-used keys when full |
| Persistence | Disabled | This is a cache, not primary storage |
| Password | Required | Set via `REDIS_PASSWORD` env var |

### Cassandra Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Replication factor | 1 (dev) / 3 (prod) | `SimpleStrategy` for dev, `NetworkTopologyStrategy` for prod |
| Compaction | `LeveledCompactionStrategy` | Better read performance for lookup-heavy workload |
| GC grace | 10 days | Time to propagate tombstones |
| Default TTL | 3 years | URLs auto-expire |

---

## 📏 Capacity Planning

### Targets

| Metric | Target |
|--------|--------|
| **Write TPS** | 400 sustained, 2,000 peak |
| **Read TPS** | 40,000 sustained, 200,000 peak |
| **Read:Write Ratio** | 100:1 |
| **Storage** (1B URLs/month, 3 years) | ~36 TB (with RF=3: ~108 TB) |
| **Cache Hit Rate** | > 95% |
| **Read Latency (p99)** | < 100 ms |
| **Write Latency (p99)** | < 500 ms |

### Storage Estimates

**Cassandra:**
- 1 URL record ≈ 500 bytes (metadata + indexes)
- 1 billion URLs = 500 GB
- 3 years × 1B URLs/month = 18 TB
- With Replication Factor 3: **54 TB total**

**Redis:**
- 10M hot URLs × 200 bytes = 2 GB
- Overhead + rate-limit data + dedup cache ≈ 4 GB per instance
- With 6-node Redis Cluster: **24 GB total**

### Compute Requirements (for 200K read TPS)

| Component | vCPU | RAM | Disk | Instances |
|-----------|------|-----|------|-----------|
| API (FastAPI) | 4 | 8 GB | 20 GB | 10 |
| Cassandra | 8 | 32 GB | 2 TB (NVMe) | 6 |
| Redis | 2 | 8 GB | 20 GB | 6 |
| Kong | 4 | 8 GB | 20 GB | 2 |
| Prometheus | 4 | 16 GB | 500 GB | 1 |
| Grafana | 2 | 4 GB | 20 GB | 1 |

### Scaling Strategy

**Horizontal (preferred):**
- **API**: Stateless — unlimited horizontal scaling behind Kong
- **Cassandra**: Add nodes to cluster, data rebalances automatically
- **Redis**: Redis Cluster with 3 masters + 3 replicas

**Vertical:**
- **Cassandra**: More RAM = larger memtable cache = faster reads; NVMe SSDs for lower latency
- **API**: Tune Uvicorn workers (`2 × CPU cores`)

---

## 📂 Project Structure

```
url-shortner/
│
├── app/                            # FastAPI application
│   ├── main.py                     #   App init, middleware stack, lifespan mgmt
│   ├── api/
│   │   └── endpoints.py            #   Route handlers (shorten, redirect, stats, health)
│   ├── core/
│   │   ├── config.py               #   Settings loaded from environment variables
│   │   └── security.py             #   URL validation, blocklist, alias checking
│   ├── db/
│   │   ├── cassandra.py            #   Cassandra connection pool & queries
│   │   └── redis.py                #   Redis connection & cache operations
│   ├── middleware/
│   │   ├── rate_limit.py           #   Sliding-window rate limiter (Redis + in-memory fallback)
│   │   └── security_headers.py     #   HSTS, CSP, X-Frame-Options, etc.
│   ├── models/
│   │   └── schemas.py              #   Pydantic request/response models with validators
│   └── services/
│       └── url_service.py          #   Core business logic (create, lookup, stats, dedup)
│
├── cassandra/
│   └── init/
│       └── 01-schema.cql           # Keyspace + table definitions (5 tables, 1 index)
│
├── config/
│   └── blocklist.txt               # Blocked domains (one per line)
│
├── k8s/                            # Kubernetes manifests (numbered for deploy order)
│   ├── 00-namespace.yaml           #   Namespace: url-shortener
│   ├── 00-secrets.yaml.example     #   Secrets template (copy, fill, apply)
│   ├── 01-cassandra.yaml           #   Cassandra StatefulSet + PVC
│   ├── 02-kong-database.yaml       #   PostgreSQL for Kong config
│   ├── 03-kong.yaml                #   Kong Deployment + Migration Job
│   ├── 04-api.yaml                 #   FastAPI Deployment + HPA (3-10 replicas)
│   ├── 05-prometheus.yaml          #   Prometheus Deployment + ConfigMap
│   ├── 06-grafana.yaml             #   Grafana Deployment
│   ├── 07-redis.yaml               #   Redis Deployment
│   └── 08-ingress-tls.yaml         #   TLS Ingress + Kong LoadBalancer Service
│
├── monitoring/
│   ├── prometheus.yml              # Prometheus scrape config (Kong → /metrics)
│   ├── grafana-datasources.yml     # Auto-provision Prometheus datasource
│   └── grafana-dashboard.json      # Pre-built dashboard (import into Grafana)
│
├── scripts/
│   ├── kong-setup.sh               # Configure Kong routes, plugins, upstream
│   ├── k8s-deploy.sh               # Full K8s deployment automation
│   ├── k8s-access.sh               # Port-forward helper for local access
│   ├── k8s-monitor.sh              # K8s monitoring helper (pod status, logs)
│   ├── k8s-ssl-setup.sh            # Generate cert and create K8s TLS Secret
│   ├── k8s-update.sh               # Build, push, and rolling-update the API
│   └── setup-https.sh              # Kong HTTPS setup (K8s environment)
│
├── ssl/
│   ├── certs/                      # Generated certs (gitignored)
│   ├── setup-ssl.sh                # Self-signed cert generation script
│   └── nginx-ssl.conf              # Nginx SSL config (alternative to Kong)
│
├── tests/
│   ├── test.sh                     # Integration test suite (curl-based)
│   ├── latency-test.sh             # Latency benchmarking (shell)
│   └── latency_test.py             # Latency benchmarking (Python, percentiles)
│
├── assets/
│   ├── postman-collection.json     # Postman collection (all endpoints)
│   ├── postman-environment.json    # Postman environment variables
│   └── POSTMAN.md                  # Postman usage guide
│
├── docs/
│   ├── ARCHITECTURE.md             # Detailed architecture & data flows
│   ├── SECURITY.md                 # Security features & checklist
│   ├── system-architecture.drawio  # Architecture diagram (draw.io)
│   └── redis-caching-architecture.drawio  # Caching layer diagram
│
├── docker-compose.yml              # Full local stack (9 services)
├── Dockerfile                      # API container (non-root, python:slim)
├── Makefile                        # Developer commands (see below)
├── requirements.txt                # Python deps: fastapi, cassandra-driver, redis, pydantic
├── .env.example                    # Environment template (safe to commit)
└── .gitignore                      # Excludes .env, ssl/certs/, k8s/00-secrets.yaml
```

---

## 📋 Makefile Commands

| Command | Description |
|---------|-------------|
| `make docker-build` | Build the API Docker image |
| `make docker-up` | Start all 9 services (waits for health checks) |
| `make docker-down` | Stop and remove all containers |
| `make docker-logs` | Follow logs from all services |
| `make kong-setup` | Configure Kong routes, plugins, and upstream |
| `make ssl-setup` | Generate self-signed SSL certificate |
| `make run` | Run FastAPI locally (no Docker, port 8000) |
| `make run-ssl` | Run FastAPI locally with HTTPS (port 8443) |
| `make cassandra-up` | Start only Cassandra |
| `make cassandra-init` | Apply CQL schema to Cassandra |
| `make cassandra-shell` | Open interactive CQL shell |
| `make cassandra-status` | Check Cassandra cluster health |
| `make k8s-deploy` | Deploy to Kubernetes |
| `make k8s-clean` | Delete the Kubernetes namespace |

---

## 🐳 Service Ports

| Service | Host Port | Container Port | Protocol |
|---------|-----------|----------------|----------|
| **Kong Proxy (HTTPS)** | `443` | `8443` | HTTPS |
| **Kong Proxy (HTTP)** | `80` | `8000` | HTTP |
| **Kong Admin** | `8001` | `8001` | HTTP |
| **FastAPI (direct)** | `8000` | `8000` | HTTP |
| **Cassandra** | `9042` | `9042` | CQL |
| **Redis** | `6379` | `6379` | RESP |
| **Prometheus** | `9090` | `9090` | HTTP |
| **Grafana** | `3000` | `3000` | HTTP |

---

## 🔧 Troubleshooting

### Docker Compose

| Problem | Check | Fix |
|---------|-------|-----|
| Cassandra won't start | `docker logs cassandra` | Wait longer; Cassandra needs ~30s to initialise |
| API shows `(unhealthy)` | `curl http://localhost:8000/health` | Check if Cassandra/Redis are healthy first |
| Kong returns `502` | `docker logs kong` | API container might not be ready; wait for health check |
| `405 Method Not Allowed` | `curl http://localhost:8001/routes` | Missing route — run `make kong-setup` |
| Can't connect to HTTPS | Check cert exists | Run `make ssl-setup` to generate certs |
| Rate limited (`429`) | Wait 60 seconds | Or restart Kong: `docker compose restart kong` |

### Kubernetes

```bash
# Pod not starting?
kubectl describe pod -n url-shortener <POD_NAME>
kubectl logs -n url-shortener <POD_NAME>

# Service not accessible?
kubectl get endpoints -n url-shortener
kubectl describe svc -n url-shortener <SERVICE_NAME>

# Check events
kubectl get events -n url-shortener --sort-by='.lastTimestamp'

# Restart a deployment
kubectl rollout restart deployment -n url-shortener <DEPLOYMENT_NAME>
```

### Disaster Recovery

| Scenario | Recovery |
|----------|----------|
| Cassandra node fails | Automatic repair (with RF ≥ 3) |
| Redis fails | Cache rebuilds from Cassandra on next request |
| Full datacenter loss | Restore Cassandra from S3 backup |
| **RTO** | 4 hours |
| **RPO** | 24 hours |

---

## 🗺 Future Enhancements

- [ ] Custom domains (bring your own domain)
- [ ] QR code generation
- [ ] Real-time analytics dashboard
- [ ] A/B testing (multiple destinations per short code)
- [ ] Geo-routing (redirect based on user location)
- [ ] API authentication (OAuth2 / JWT / API keys)
- [ ] Webhooks (notify on click events)
- [ ] CDN integration (CloudFlare edge caching)
- [ ] Multi-region deployment

---

## 📄 License

MIT
