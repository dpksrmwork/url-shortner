# Kubernetes Deployment Guide

## Prerequisites

- Kubernetes cluster (minikube, kind, or cloud provider)
- kubectl configured
- Docker

## Quick Deploy

```bash
./k8s-deploy.sh
```

## Manual Deployment

### 1. Build Image

```bash
docker build -t url-shortener-api:latest .
```

### 2. Deploy Services

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-cassandra.yaml
kubectl apply -f k8s/02-kong-database.yaml

# Wait for databases
kubectl wait --for=condition=ready pod -l app=cassandra -n url-shortener --timeout=300s
kubectl wait --for=condition=ready pod -l app=kong-database -n url-shortener --timeout=120s

kubectl apply -f k8s/03-kong.yaml
kubectl wait --for=condition=complete job/kong-migration -n url-shortener --timeout=120s

kubectl apply -f k8s/04-api.yaml
kubectl apply -f k8s/05-prometheus.yaml
kubectl apply -f k8s/06-grafana.yaml
```

### 3. Initialize Cassandra

```bash
CASSANDRA_POD=$(kubectl get pod -n url-shortener -l app=cassandra -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i $CASSANDRA_POD -n url-shortener -- cqlsh < cassandra/init/01-schema.cql
```

### 4. Configure Kong

```bash
kubectl port-forward svc/kong -n url-shortener 8001:8001 &

# Run kong-setup.sh or manually configure
curl -X POST http://localhost:8001/upstreams --data name=url-shortener-upstream
curl -X POST http://localhost:8001/upstreams/url-shortener-upstream/targets \
  --data target=api.url-shortener.svc.cluster.local:8000
# ... (see k8s-deploy.sh for full config)
```

## Access Services

### Port Forwarding

```bash
# Kong Proxy
kubectl port-forward svc/kong -n url-shortener 8000:8000

# Kong Admin
kubectl port-forward svc/kong -n url-shortener 8001:8001

# Prometheus
kubectl port-forward svc/prometheus -n url-shortener 9090:9090

# Grafana
kubectl port-forward svc/grafana -n url-shortener 3000:3000
```

### Test

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Kubernetes Cluster                 │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Kong Service (LoadBalancer)             │  │
│  │  Port 8000, 8001                         │  │
│  └────────────┬─────────────────────────────┘  │
│               │                                 │
│               ▼                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Kong Deployment (1 replica)             │  │
│  └────────────┬─────────────────────────────┘  │
│               │                                 │
│               ▼                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  API Service (ClusterIP)                 │  │
│  └────────────┬─────────────────────────────┘  │
│               │                                 │
│               ▼                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  API Deployment (3 replicas)             │  │
│  │  + HorizontalPodAutoscaler (3-10)        │  │
│  └────────────┬─────────────────────────────┘  │
│               │                                 │
│               ▼                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Cassandra StatefulSet (1 replica)       │  │
│  │  + PersistentVolume (10Gi)               │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Prometheus (NodePort 30090)             │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Grafana (NodePort 30300)                │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Scaling

### Manual Scaling

```bash
kubectl scale deployment api -n url-shortener --replicas=5
```

### Auto-scaling

HPA is configured to scale between 3-10 replicas based on CPU usage (70%).

```bash
kubectl get hpa -n url-shortener
```

## Monitoring

```bash
# View logs
kubectl logs -f deployment/api -n url-shortener
kubectl logs -f deployment/kong -n url-shortener

# View metrics
kubectl top pods -n url-shortener
kubectl top nodes
```

## Cleanup

```bash
kubectl delete namespace url-shortener
```

## Production Considerations

### 1. Persistent Storage

Update Cassandra to use proper StorageClass:

```yaml
volumeClaimTemplates:
  - metadata:
      name: cassandra-data
    spec:
      storageClassName: fast-ssd  # Your storage class
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 100Gi
```

### 2. High Availability

Scale Cassandra:

```yaml
spec:
  replicas: 3  # For HA
```

### 3. Resource Limits

Add to API deployment:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### 4. Ingress

Replace Kong LoadBalancer with Ingress:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: url-shortener
  namespace: url-shortener
spec:
  rules:
  - host: short.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kong
            port:
              number: 8000
```

### 5. Secrets

Use Kubernetes Secrets for passwords:

```bash
kubectl create secret generic kong-db-secret \
  --from-literal=password=kongpass \
  -n url-shortener
```

### 6. Health Checks

Already configured in deployments with liveness/readiness probes.

## Troubleshooting

```bash
# Check pod status
kubectl get pods -n url-shortener

# Describe pod
kubectl describe pod <pod-name> -n url-shortener

# View logs
kubectl logs <pod-name> -n url-shortener

# Execute into pod
kubectl exec -it <pod-name> -n url-shortener -- /bin/bash

# Check services
kubectl get svc -n url-shortener

# Check events
kubectl get events -n url-shortener --sort-by='.lastTimestamp'
```
