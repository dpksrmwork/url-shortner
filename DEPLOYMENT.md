# Kong API Gateway Deployment

## Architecture

```
Client → Kong Gateway (Port 8000) → FastAPI Containers (3 replicas) → Cassandra
         ├─ Rate Limiting
         ├─ Caching
         ├─ Load Balancing
         └─ Monitoring
```

## Components

- **Kong Gateway** - API Gateway (port 8000)
- **Kong Admin API** - Configuration (port 8001)
- **PostgreSQL** - Kong database
- **Cassandra** - Application database
- **FastAPI** - 3 replicas with load balancing

## Quick Start

### 1. Build and Start All Services

```bash
make docker-build
make docker-up
```

### 2. Initialize Cassandra Schema

```bash
make cassandra-init
```

### 3. Configure Kong

```bash
make kong-setup
```

### 4. Test the Setup

```bash
# Create short URL (through Kong)
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Redirect (cached after first request)
curl -L http://localhost:8000/abc123

# Get stats
curl http://localhost:8000/stats/abc123
```

## Kong Features Enabled

### 1. Load Balancing
- 3 FastAPI instances
- Round-robin distribution
- Health checks

### 2. Rate Limiting
- 100 requests/minute per IP
- 10,000 requests/hour per IP

### 3. Proxy Caching
- 5-minute cache for GET requests
- Memory-based strategy
- Reduces Cassandra load

### 4. CORS
- Cross-origin requests enabled
- Configurable origins

### 5. Prometheus Metrics
- Available at: http://localhost:8001/metrics
- Request counts, latencies, status codes

## Management

### View Logs
```bash
make docker-logs
```

### Stop Services
```bash
make docker-down
```

### Kong Admin API

```bash
# List services
curl http://localhost:8001/services

# List routes
curl http://localhost:8001/routes

# List plugins
curl http://localhost:8001/plugins

# View metrics
curl http://localhost:8001/metrics
```

## Scaling

### Scale FastAPI Instances

Edit `docker-compose.yml`:
```yaml
api:
  deploy:
    replicas: 5  # Change from 3 to 5
```

Then:
```bash
make docker-down
make docker-up
make kong-setup
```

## Production Considerations

1. **SSL/TLS** - Add certificates to Kong
2. **Authentication** - Enable key-auth or JWT plugin
3. **Database** - Use external PostgreSQL and Cassandra clusters
4. **Monitoring** - Integrate with Prometheus/Grafana
5. **Logging** - Ship logs to ELK/Splunk
6. **Backup** - Regular database backups
