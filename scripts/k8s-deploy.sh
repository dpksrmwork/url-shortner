#!/bin/bash

set -e

echo "=========================================="
echo "Deploying URL Shortener to Kubernetes"
echo "=========================================="
echo ""

# Build Docker image
echo "1. Building Docker image..."
docker build -t url-shortener-api:latest .
echo "✓ Image built"
echo ""

# Apply manifests
echo "2. Applying Kubernetes manifests..."
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-cassandra.yaml
kubectl apply -f k8s/02-kong-database.yaml

echo "Waiting for databases to be ready..."
kubectl wait --for=condition=ready pod -l app=cassandra -n url-shortener --timeout=300s
kubectl wait --for=condition=ready pod -l app=kong-database -n url-shortener --timeout=120s

kubectl apply -f k8s/03-kong.yaml
echo "Waiting for Kong migration..."
kubectl wait --for=condition=complete job/kong-migration -n url-shortener --timeout=120s

kubectl apply -f k8s/04-api.yaml
kubectl apply -f k8s/05-prometheus.yaml
kubectl apply -f k8s/06-grafana.yaml

echo "✓ All manifests applied"
echo ""

# Initialize Cassandra
echo "3. Initializing Cassandra schema..."
sleep 10
CASSANDRA_POD=$(kubectl get pod -n url-shortener -l app=cassandra -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i $CASSANDRA_POD -n url-shortener -- cqlsh < cassandra/init/01-schema.cql
echo "✓ Schema initialized"
echo ""

# Wait for all pods
echo "4. Waiting for all pods to be ready..."
kubectl wait --for=condition=ready pod -l app=api -n url-shortener --timeout=120s
kubectl wait --for=condition=ready pod -l app=kong -n url-shortener --timeout=120s
echo "✓ All pods ready"
echo ""

# Configure Kong
echo "5. Configuring Kong..."
KONG_ADMIN=$(kubectl get svc kong -n url-shortener -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$KONG_ADMIN" ]; then
    KONG_ADMIN="localhost"
    kubectl port-forward svc/kong -n url-shortener 8001:8001 &
    sleep 3
fi

# Create upstream
curl -s -X POST http://$KONG_ADMIN:8001/upstreams --data name=url-shortener-upstream > /dev/null

# Add API service as target
curl -s -X POST http://$KONG_ADMIN:8001/upstreams/url-shortener-upstream/targets \
  --data target=api.url-shortener.svc.cluster.local:8000 > /dev/null

# Create service
curl -s -X POST http://$KONG_ADMIN:8001/services \
  --data name=url-shortener-service \
  --data host=url-shortener-upstream \
  --data port=8000 > /dev/null

# Create routes
curl -s -X POST http://$KONG_ADMIN:8001/services/url-shortener-service/routes \
  --data 'paths[]=/shorten' \
  --data 'methods[]=POST' > /dev/null

curl -s -X POST http://$KONG_ADMIN:8001/services/url-shortener-service/routes \
  --data 'paths[]=/stats' > /dev/null

curl -s -X POST http://$KONG_ADMIN:8001/services/url-shortener-service/routes \
  --data 'paths[]=/' \
  --data strip_path=false > /dev/null

# Add plugins
curl -s -X POST http://$KONG_ADMIN:8001/services/url-shortener-service/plugins \
  --data name=rate-limiting \
  --data config.minute=100 \
  --data config.hour=10000 > /dev/null

curl -s -X POST http://$KONG_ADMIN:8001/plugins \
  --data name=prometheus > /dev/null

echo "✓ Kong configured"
echo ""

# Display info
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Services:"
kubectl get svc -n url-shortener
echo ""
echo "Pods:"
kubectl get pods -n url-shortener
echo ""
echo "Access points:"
echo "  • Kong Proxy:   kubectl port-forward svc/kong -n url-shortener 8000:8000"
echo "  • Kong Admin:   kubectl port-forward svc/kong -n url-shortener 8001:8001"
echo "  • Prometheus:   kubectl port-forward svc/prometheus -n url-shortener 9090:9090"
echo "  • Grafana:      kubectl port-forward svc/grafana -n url-shortener 3000:3000"
echo ""
echo "Test:"
echo "  curl -X POST http://localhost:8000/shorten \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"url\": \"https://example.com\"}'"
