#!/bin/bash

# URL Shortener - Kubernetes Monitoring Dashboard

echo "=========================================="
echo "URL Shortener - Monitoring Dashboard"
echo "=========================================="
echo ""

# Check cluster
echo "📊 Cluster Info:"
kubectl cluster-info | head -2
echo ""

# Namespace resources
echo "📦 Resources in url-shortener namespace:"
kubectl get all -n url-shortener
echo ""

# Pod status
echo "🔍 Pod Details:"
kubectl get pods -n url-shortener -o wide
echo ""

# Resource usage
echo "💻 Resource Usage:"
kubectl top pods -n url-shortener 2>/dev/null || echo "Metrics server not available"
echo ""

# HPA status
echo "📈 Auto-scaling Status:"
kubectl get hpa -n url-shortener
echo ""

# Service endpoints
echo "🌐 Service Endpoints:"
kubectl get svc -n url-shortener
echo ""

# Recent events
echo "📋 Recent Events:"
kubectl get events -n url-shortener --sort-by='.lastTimestamp' | tail -10
echo ""

# Access instructions
echo "=========================================="
echo "🔗 Access Services:"
echo "=========================================="
echo ""
echo "1. Prometheus (Metrics):"
echo "   kubectl port-forward svc/prometheus -n url-shortener 9090:9090"
echo "   Open: http://localhost:9090"
echo ""
echo "2. Grafana (Dashboards):"
echo "   kubectl port-forward svc/grafana -n url-shortener 3000:3000"
echo "   Open: http://localhost:3000 (admin/admin)"
echo ""
echo "3. Kong Admin (API Gateway):"
echo "   kubectl port-forward svc/kong -n url-shortener 8001:8001"
echo "   Open: http://localhost:8001"
echo ""
echo "4. API (via Kong):"
echo "   kubectl port-forward svc/kong -n url-shortener 8000:8000"
echo "   Test: curl -X POST http://localhost:8000/shorten -H 'Content-Type: application/json' -d '{\"url\": \"https://example.com\"}'"
echo ""

# Monitoring commands
echo "=========================================="
echo "📊 Monitoring Commands:"
echo "=========================================="
echo ""
echo "Watch pods:"
echo "  kubectl get pods -n url-shortener -w"
echo ""
echo "Stream logs (all API pods):"
echo "  kubectl logs -f -n url-shortener -l app=api"
echo ""
echo "Stream logs (specific pod):"
echo "  kubectl logs -f -n url-shortener <pod-name>"
echo ""
echo "Describe pod:"
echo "  kubectl describe pod -n url-shortener <pod-name>"
echo ""
echo "Execute into pod:"
echo "  kubectl exec -it -n url-shortener <pod-name> -- /bin/bash"
echo ""
echo "Check HPA:"
echo "  kubectl get hpa -n url-shortener -w"
echo ""
echo "Resource usage:"
echo "  kubectl top pods -n url-shortener"
echo "  kubectl top nodes"
echo ""
