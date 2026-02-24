#!/bin/bash

set -e

echo "🚀 Rolling out changes to Kubernetes deployment"
echo ""

# Configuration
NAMESPACE="url-shortener"
IMAGE_NAME="url-shortener-api"
IMAGE_TAG="v$(date +%Y%m%d-%H%M%S)"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found"
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ docker not found"
    exit 1
fi

echo "📦 Step 1: Build new Docker image"
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
docker build -t $IMAGE_NAME:$IMAGE_TAG .
docker tag $IMAGE_NAME:$IMAGE_TAG $IMAGE_NAME:latest
echo "✅ Image built"
echo ""

echo "📤 Step 2: Push image to registry"
echo "Choose your option:"
echo "  1) Docker Hub (requires login)"
echo "  2) Minikube (local only)"
echo "  3) Skip (image already in registry)"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        read -p "Enter Docker Hub username: " DOCKER_USER
        IMAGE_FULL="$DOCKER_USER/$IMAGE_NAME:$IMAGE_TAG"
        docker tag $IMAGE_NAME:$IMAGE_TAG $IMAGE_FULL
        docker push $IMAGE_FULL
        echo "✅ Pushed to Docker Hub: $IMAGE_FULL"
        ;;
    2)
        eval $(minikube docker-env)
        docker build -t $IMAGE_NAME:$IMAGE_TAG .
        IMAGE_FULL="$IMAGE_NAME:$IMAGE_TAG"
        echo "✅ Built in Minikube"
        ;;
    3)
        IMAGE_FULL="$IMAGE_NAME:$IMAGE_TAG"
        echo "⏭️  Skipped push"
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac
echo ""

echo "🔄 Step 3: Update Kubernetes deployment"
kubectl set image deployment/api \
    api=$IMAGE_FULL \
    -n $NAMESPACE

echo "✅ Deployment updated"
echo ""

echo "⏳ Step 4: Wait for rollout to complete"
kubectl rollout status deployment/api -n $NAMESPACE --timeout=5m

echo "✅ Rollout complete"
echo ""

echo "📊 Step 5: Verify deployment"
echo ""
echo "Pods:"
kubectl get pods -n $NAMESPACE -l app=api
echo ""
echo "Recent events:"
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -5
echo ""

echo "✅ Deployment successful!"
echo ""
echo "Test the health endpoint:"
echo "  kubectl port-forward -n $NAMESPACE svc/kong 8000:80"
echo "  curl http://localhost:8000/health"
