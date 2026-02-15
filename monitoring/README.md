# Monitoring Setup

## Components

- **Prometheus** - Metrics collection (Port 9090)
- **Grafana** - Visualization dashboards (Port 3000)
- **Kong Prometheus Plugin** - Exports Kong metrics

## Access

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Kong Metrics**: http://localhost:8001/metrics

## Key Metrics

### Kong Metrics (from Prometheus plugin)

```promql
# Request rate
rate(kong_http_requests_total[5m])

# Request latency (p95)
histogram_quantile(0.95, rate(kong_latency_bucket[5m]))

# Error rate
rate(kong_http_requests_total{code=~"5.."}[5m])

# Bandwidth
rate(kong_bandwidth_bytes[5m])

# Active connections
kong_nginx_connections_active
```

### Useful Queries

**Requests per second by route:**
```promql
sum(rate(kong_http_requests_total[5m])) by (route)
```

**95th percentile latency:**
```promql
histogram_quantile(0.95, sum(rate(kong_latency_bucket[5m])) by (le))
```

**Error rate percentage:**
```promql
sum(rate(kong_http_requests_total{code=~"5.."}[5m])) / sum(rate(kong_http_requests_total[5m])) * 100
```

**Cache hit rate:**
```promql
sum(rate(kong_http_requests_total{cache_status="Hit"}[5m])) / sum(rate(kong_http_requests_total[5m])) * 100
```

## Grafana Dashboard Setup

### 1. Login to Grafana
- URL: http://localhost:3000
- Username: `admin`
- Password: `admin`

### 2. Create Dashboard

Add panels with these queries:

**Panel 1: Request Rate**
- Query: `sum(rate(kong_http_requests_total[5m]))`
- Visualization: Graph
- Title: "Requests per Second"

**Panel 2: Latency (p50, p95, p99)**
- Query 1: `histogram_quantile(0.50, sum(rate(kong_latency_bucket[5m])) by (le))`
- Query 2: `histogram_quantile(0.95, sum(rate(kong_latency_bucket[5m])) by (le))`
- Query 3: `histogram_quantile(0.99, sum(rate(kong_latency_bucket[5m])) by (le))`
- Visualization: Graph
- Title: "Response Latency"

**Panel 3: Status Codes**
- Query: `sum(rate(kong_http_requests_total[5m])) by (code)`
- Visualization: Pie Chart
- Title: "HTTP Status Codes"

**Panel 4: Error Rate**
- Query: `sum(rate(kong_http_requests_total{code=~"5.."}[5m]))`
- Visualization: Stat
- Title: "5xx Errors/sec"

**Panel 5: Cache Performance**
- Query: `sum(rate(kong_http_requests_total[5m])) by (cache_status)`
- Visualization: Bar Chart
- Title: "Cache Hit/Miss"

**Panel 6: Bandwidth**
- Query: `sum(rate(kong_bandwidth_bytes[5m]))`
- Visualization: Graph
- Title: "Bandwidth (bytes/sec)"

## Alerts

### Prometheus Alert Rules

Create `monitoring/alert-rules.yml`:

```yaml
groups:
  - name: url_shortener_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: sum(rate(kong_http_requests_total{code=~"5.."}[5m])) / sum(rate(kong_http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }}%"

      - alert: HighLatency
        expr: histogram_quantile(0.95, sum(rate(kong_latency_bucket[5m])) by (le)) > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
          description: "P95 latency is {{ $value }}ms"

      - alert: LowCacheHitRate
        expr: sum(rate(kong_http_requests_total{cache_status="Hit"}[5m])) / sum(rate(kong_http_requests_total[5m])) < 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low cache hit rate"
          description: "Cache hit rate is {{ $value }}%"
```

## Testing Metrics

```bash
# Generate traffic
for i in {1..100}; do
  curl -X POST http://localhost:8000/shorten \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"https://example.com/$i\"}"
done

# View metrics
curl http://localhost:8001/metrics

# Check Prometheus targets
open http://localhost:9090/targets

# View Grafana
open http://localhost:3000
```

## Production Recommendations

1. **Retention** - Configure Prometheus retention (default 15 days)
2. **Alerting** - Set up Alertmanager for notifications
3. **Exporters** - Add node_exporter for system metrics
4. **Cassandra Metrics** - Add cassandra_exporter
5. **Log Aggregation** - Add ELK stack or Loki
