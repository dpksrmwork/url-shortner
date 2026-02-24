#!/bin/bash

# Wait for Kong to be ready
echo "Waiting for Kong to be ready..."
until curl -s http://localhost:8001/status > /dev/null; do
  sleep 2
done
echo "Kong is ready!"

# Create Upstream (load balancer)
echo "Creating upstream..."
curl -i -X POST http://localhost:8001/upstreams \
  --data name=url-shortener-upstream

# Add targets (FastAPI instances)
echo "Adding targets to upstream..."
for i in {1..3}; do
  curl -i -X POST http://localhost:8001/upstreams/url-shortener-upstream/targets \
    --data target=api:8000 \
    --data weight=100
done

# Create Service
echo "Creating service..."
curl -i -X POST http://localhost:8001/services \
  --data name=url-shortener-service \
  --data host=url-shortener-upstream \
  --data port=8000 \
  --data protocol=http

# Create Routes
echo "Creating routes..."

# Route for shorten endpoint
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/shorten' \
  --data 'methods[]=POST' \
  --data name=shorten-route \
  --data strip_path=false

# Route for stats endpoint
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/stats' \
  --data name=stats-route \
  --data strip_path=false

# Route for health endpoint
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/health' \
  --data 'methods[]=GET' \
  --data name=health-route \
  --data strip_path=false

# Route for docs endpoint
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/docs' \
  --data 'methods[]=GET' \
  --data name=docs-route \
  --data strip_path=false

# Route for openapi.json
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/openapi.json' \
  --data 'methods[]=GET' \
  --data name=openapi-route \
  --data strip_path=false

# Route for redirect (catch-all)
curl -i -X POST http://localhost:8001/services/url-shortener-service/routes \
  --data 'paths[]=/' \
  --data name=redirect-route \
  --data strip_path=false

# Add Rate Limiting Plugin
echo "Adding rate limiting plugin..."
curl -i -X POST http://localhost:8001/services/url-shortener-service/plugins \
  --data name=rate-limiting \
  --data config.minute=100 \
  --data config.hour=10000 \
  --data config.policy=local

# Add Proxy Cache Plugin (for GET requests)
echo "Adding proxy cache plugin..."
curl -i -X POST http://localhost:8001/routes/redirect-route/plugins \
  --data name=proxy-cache \
  --data config.strategy=memory \
  --data config.content_type[]="application/json" \
  --data config.cache_ttl=300 \
  --data config.cache_control=true

# Add CORS Plugin
echo "Adding CORS plugin..."
curl -i -X POST http://localhost:8001/services/url-shortener-service/plugins \
  --data name=cors \
  --data config.origins=* \
  --data config.methods=GET \
  --data config.methods=POST \
  --data config.methods=OPTIONS \
  --data config.headers=Accept \
  --data config.headers=Content-Type \
  --data config.exposed_headers=X-Auth-Token \
  --data config.credentials=true \
  --data config.max_age=3600

# Add Prometheus Plugin
echo "Adding prometheus plugin..."
curl -i -X POST http://localhost:8001/plugins \
  --data name=prometheus

echo "Kong configuration completed!"
echo ""
echo "Access points:"
echo "  - HTTP Gateway:  http://localhost"
echo "  - HTTPS Gateway: https://localhost"
echo "  - Kong Admin:    http://localhost:8001"
echo "  - Prometheus:    http://localhost:8001/metrics"
