# Monitoring

Prometheus and Grafana configuration for URL shortener metrics.

## Files

- `prometheus.yml` - Prometheus scrape configuration
- `grafana-datasources.yml` - Grafana datasource configuration
- `grafana-dashboard.json` - Pre-built Grafana dashboard

## Metrics

### Kong Metrics (via Prometheus plugin)
- `kong_http_status` - HTTP status codes
- `kong_latency` - Request/upstream/Kong latency
- `kong_bandwidth` - Request/response sizes
- `kong_datastore_reachable` - Database health

## Dashboard Panels

1. **Total Requests per Second** - Request rate
2. **Latency** - p50, p95, p99 latency
3. **HTTP Status Codes** - 2xx, 4xx, 5xx breakdown
4. **Cache Hit Rate** - Redis cache effectiveness

## Access

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/password from .env)

## Import Dashboard

1. Open Grafana at http://localhost:3000
2. Go to Dashboards → Import
3. Upload `grafana-dashboard.json`
4. Select Prometheus datasource
5. Click Import
