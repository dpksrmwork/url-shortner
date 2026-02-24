#!/bin/bash

set -e

echo "🔐 Setting up SSL/TLS for Kubernetes deployment"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace url-shortener &> /dev/null; then
    echo "❌ Namespace 'url-shortener' not found. Please create it first:"
    echo "   kubectl apply -f k8s/00-namespace.yaml"
    exit 1
fi

echo "📝 Generating self-signed SSL certificate..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/tls.key \
  -out /tmp/tls.crt \
  -subj "/CN=url-shortener.local/O=url-shortener" \
  2>/dev/null

echo "✅ Certificate generated"
echo ""

# Check if secret already exists
if kubectl get secret url-shortener-tls -n url-shortener &> /dev/null; then
    echo "⚠️  TLS secret already exists. Deleting old secret..."
    kubectl delete secret url-shortener-tls -n url-shortener
fi

echo "📦 Creating Kubernetes TLS secret..."
kubectl create secret tls url-shortener-tls \
  --namespace=url-shortener \
  --key=/tmp/tls.key \
  --cert=/tmp/tls.crt

echo "✅ TLS secret created"
echo ""

# Cleanup temporary files
rm -f /tmp/tls.key /tmp/tls.crt
echo "🧹 Cleaned up temporary files"
echo ""

echo "✅ SSL/TLS setup complete!"
echo ""
echo "Next steps:"
echo "1. Update Kong service to use HTTPS (port 443)"
echo "2. Configure Kong certificate:"
echo ""
echo "   # Get Kong admin service"
echo "   kubectl port-forward -n url-shortener svc/kong-admin 8001:8001 &"
echo ""
echo "   # Upload certificate to Kong"
echo "   kubectl get secret url-shortener-tls -n url-shortener -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/cert.pem"
echo "   kubectl get secret url-shortener-tls -n url-shortener -o jsonpath='{.data.tls\.key}' | base64 -d > /tmp/key.pem"
echo ""
echo "   curl -X POST http://localhost:8001/certificates \\"
echo "     -F 'cert=@/tmp/cert.pem' \\"
echo "     -F 'key=@/tmp/key.pem' \\"
echo "     -F 'snis=url-shortener.local'"
echo ""
echo "   rm /tmp/cert.pem /tmp/key.pem"
echo ""
echo "3. Access via HTTPS:"
echo "   kubectl port-forward -n url-shortener svc/kong 8443:443"
echo "   curl -k https://localhost:8443/health"
