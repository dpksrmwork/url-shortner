#!/bin/bash

echo "Starting port-forwards for all monitoring services..."
echo ""

# Kill existing port-forwards
pkill -f "port-forward.*url-shortener" 2>/dev/null

# Start port-forwards in background
kubectl port-forward svc/prometheus -n url-shortener 9090:9090 > /dev/null 2>&1 &
kubectl port-forward svc/grafana -n url-shortener 3000:3000 > /dev/null 2>&1 &
kubectl port-forward svc/kong -n url-shortener 8000:8000 8001:8001 > /dev/null 2>&1 &

sleep 3

echo "✅ All services accessible:"
echo ""
echo "📊 Prometheus:  http://localhost:9090"
echo "📈 Grafana:     http://localhost:3000 (admin/admin)"
echo "🔧 Kong Admin:  http://localhost:8001"
echo "🚀 API Gateway: http://localhost:8000"
echo ""
echo "Test API:"
echo "  curl -X POST http://localhost:8000/shorten \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"url\": \"https://example.com\"}'"
echo ""
echo "Press Ctrl+C to stop all port-forwards"
echo ""

# Wait for interrupt
trap "pkill -f 'port-forward.*url-shortener'; echo 'Stopped all port-forwards'; exit" INT
wait
