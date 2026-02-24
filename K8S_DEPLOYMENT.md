# Kubernetes Deployment Guide - Step by Step

## Prerequisites

1. **Kubernetes cluster** (minikube, kind, or cloud provider)
2. **kubectl** installed and configured
3. **Docker** (for building images)

Check your setup:
```bash
kubectl version --client
kubectl cluster-info
```

---

## Step 1: Create Namespace

```bash
kubectl apply -f k8s/00-namespace.yaml
```

Verify:
```bash
kubectl get namespaces | grep url-shortener
```

---

## Step 2: Create Secrets

**Option A: Using the YAML file (NOT RECOMMENDED for production)**

Edit `k8s/00-secrets.yaml` and replace `CHANGE_ME` with actual passwords:
```bash
nano k8s/00-secrets.yaml
kubectl apply -f k8s/00-secrets.yaml
```

**Option B: Using kubectl (RECOMMENDED)**

```bash
kubectl create secret generic url-shortener-secrets \
  --namespace=url-shortener \
  --from-literal=kong-pg-password=YOUR_SECURE_PASSWORD \
  --from-literal=grafana-admin-password=YOUR_SECURE_PASSWORD \
  --from-literal=redis-password=YOUR_SECURE_PASSWORD
```

Verify:
```bash
kubectl get secrets -n url-shortener
```

---

## Step 3: Deploy Cassandra

```bash
kubectl apply -f k8s/01-cassandra.yaml
```

Wait for Cassandra to be ready (takes 2-3 minutes):
```bash
kubectl get pods -n url-shortener -w
# Wait until cassandra-0 shows 1/1 RUNNING
# Press Ctrl+C to exit watch mode
```

Check logs:
```bash
kubectl logs -n url-shortener cassandra-0
```

Initialize schema:
```bash
kubectl exec -n url-shortener cassandra-0 -- cqlsh -f /schema/01-schema.cql
```

Verify schema:
```bash
kubectl exec -n url-shortener cassandra-0 -- cqlsh -e "DESCRIBE KEYSPACE url_shortener;"
```

---

## Step 4: Deploy Kong Database (PostgreSQL)

```bash
kubectl apply -f k8s/02-kong-database.yaml
```

Wait for PostgreSQL to be ready:
```bash
kubectl get pods -n url-shortener -l app=kong-database -w
# Wait until RUNNING
```

Verify:
```bash
kubectl logs -n url-shortener -l app=kong-database
```

---

## Step 5: Deploy Kong API Gateway

```bash
kubectl apply -f k8s/03-kong.yaml
```

This will:
1. Run Kong migrations (init job)
2. Start Kong gateway

Wait for Kong to be ready:
```bash
kubectl get pods -n url-shortener -l app=kong -w
```

Check Kong migration job:
```bash
kubectl get jobs -n url-shortener
kubectl logs -n url-shortener job/kong-migration
```

Verify Kong is running:
```bash
kubectl logs -n url-shortener -l app=kong
```

---

## Step 6: Deploy Redis

```bash
kubectl apply -f k8s/07-redis.yaml
```

Wait for Redis:
```bash
kubectl get pods -n url-shortener -l app=redis -w
```

Test Redis connection:
```bash
kubectl exec -n url-shortener -it $(kubectl get pod -n url-shortener -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli -a YOUR_REDIS_PASSWORD ping
# Should return: PONG
```

---

## Step 7: Build and Push API Docker Image

**Option A: Using Docker Hub**

```bash
# Build image
docker build -t YOUR_DOCKERHUB_USERNAME/url-shortener-api:latest .

# Push to Docker Hub
docker login
docker push YOUR_DOCKERHUB_USERNAME/url-shortener-api:latest
```

**Option B: Using Minikube (local testing)**

```bash
# Use minikube's Docker daemon
eval $(minikube docker-env)

# Build image
docker build -t url-shortener-api:latest .
```

Update `k8s/04-api.yaml` with your image name:
```yaml
image: YOUR_DOCKERHUB_USERNAME/url-shortener-api:latest
# OR for minikube:
image: url-shortener-api:latest
imagePullPolicy: Never
```

---

## Step 8: Deploy API Application

```bash
kubectl apply -f k8s/04-api.yaml
```

Wait for API pods:
```bash
kubectl get pods -n url-shortener -l app=url-shortener-api -w
```

Check logs:
```bash
kubectl logs -n url-shortener -l app=url-shortener-api --tail=50
```

---

## Step 9: Deploy Prometheus

```bash
kubectl apply -f k8s/05-prometheus.yaml
```

Wait for Prometheus:
```bash
kubectl get pods -n url-shortener -l app=prometheus -w
```

---

## Step 10: Deploy Grafana

```bash
kubectl apply -f k8s/06-grafana.yaml
```

Wait for Grafana:
```bash
kubectl get pods -n url-shortener -l app=grafana -w
```

---

## Step 11: Configure Kong Routes

Run the Kong setup script:
```bash
./scripts/kong-setup.sh
```

Or manually:
```bash
# Get Kong admin service
KONG_ADMIN=$(kubectl get svc -n url-shortener kong-admin -o jsonpath='{.spec.clusterIP}')

# Create service
kubectl run -n url-shortener curl --image=curlimages/curl --rm -it --restart=Never -- \
  curl -X POST http://$KONG_ADMIN:8001/services \
  -d name=url-shortener \
  -d url=http://url-shortener-api:8000

# Create route
kubectl run -n url-shortener curl --image=curlimages/curl --rm -it --restart=Never -- \
  curl -X POST http://$KONG_ADMIN:8001/services/url-shortener/routes \
  -d paths[]=/
```

---

## Step 12: Access Services

### Port Forward (for local testing)

**API via Kong:**
```bash
kubectl port-forward -n url-shortener svc/kong 8000:80
```
Access: http://localhost:8000

**Grafana:**
```bash
kubectl port-forward -n url-shortener svc/grafana 3000:3000
```
Access: http://localhost:3000 (admin/YOUR_PASSWORD)

**Prometheus:**
```bash
kubectl port-forward -n url-shortener svc/prometheus 9090:9090
```
Access: http://localhost:9090

### Using LoadBalancer (cloud providers)

If using cloud provider, get external IPs:
```bash
kubectl get svc -n url-shortener
```

---

## Step 13: Test the Deployment

```bash
# Create short URL
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/example/repo"}'

# Test redirect
curl -L http://localhost:8000/SHORT_CODE

# Get stats
curl http://localhost:8000/stats/SHORT_CODE
```

---

## Verification Checklist

```bash
# Check all pods are running
kubectl get pods -n url-shortener

# Check all services
kubectl get svc -n url-shortener

# Check secrets
kubectl get secrets -n url-shortener

# Check persistent volumes
kubectl get pvc -n url-shortener

# View all resources
kubectl get all -n url-shortener
```

---

## Troubleshooting

### Pod not starting
```bash
kubectl describe pod -n url-shortener POD_NAME
kubectl logs -n url-shortener POD_NAME
```

### Service not accessible
```bash
kubectl get endpoints -n url-shortener
kubectl describe svc -n url-shortener SERVICE_NAME
```

### Check events
```bash
kubectl get events -n url-shortener --sort-by='.lastTimestamp'
```

### Restart a deployment
```bash
kubectl rollout restart deployment -n url-shortener DEPLOYMENT_NAME
```

---

## Cleanup

To remove everything:
```bash
kubectl delete namespace url-shortener
```

To remove specific components:
```bash
kubectl delete -f k8s/06-grafana.yaml
kubectl delete -f k8s/05-prometheus.yaml
kubectl delete -f k8s/04-api.yaml
kubectl delete -f k8s/07-redis.yaml
kubectl delete -f k8s/03-kong.yaml
kubectl delete -f k8s/02-kong-database.yaml
kubectl delete -f k8s/01-cassandra.yaml
kubectl delete -f k8s/00-secrets.yaml
kubectl delete -f k8s/00-namespace.yaml
```

---

## Production Considerations

1. **Use proper secrets management** (Vault, AWS Secrets Manager)
2. **Set resource limits** in deployment YAMLs
3. **Configure persistent volumes** for data persistence
4. **Set up ingress** instead of port-forward
5. **Enable TLS/SSL** on Kong
6. **Configure horizontal pod autoscaling**
7. **Set up monitoring alerts**
8. **Configure backup strategy** for Cassandra
9. **Use private container registry**
10. **Implement network policies**
