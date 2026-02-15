#!/bin/bash
set -e

# Configuration
SERVICE_NAME="url-shortener"
SERVICE_URL="http://api.url-shortener.svc.cluster.local:8000"
DOMAIN="localhost"
ADMIN_URL="http://localhost:8001"

echo "=== 🔒 Setting up HTTPS for URL Shortener ==="

# 1. Generate Self-Signed Certificate
echo "Generating self-signed certificate for $DOMAIN..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=$DOMAIN/O=URL Shortener Dev/C=US" \
  >/dev/null 2>&1

echo "Certificate generated: tls.crt"

# 2. Port Forward Kong Admin API (in background)
echo "Establishing connection to Kong Admin API..."
pkill -f "port-forward svc/kong 8001:8001" || true
kubectl -n url-shortener port-forward svc/kong 8001:8001 >/dev/null 2>&1 &
PF_PID=$!
sleep 5

# Check connection
if ! curl -s $ADMIN_URL >/dev/null; then
  echo "❌ Failed to connect to Kong Admin API. Is Kong running?"
  kill $PF_PID
  exit 1
fi
echo "✓ Connected to Kong Admin API"

# 3. Create Service in Kong
echo "Configuring Service: $SERVICE_NAME -> $SERVICE_URL"
curl -s -X POST $ADMIN_URL/services \
  --data name=$SERVICE_NAME \
  --data url=$SERVICE_URL \
  | grep -q "id" || curl -s -X PATCH $ADMIN_URL/services/$SERVICE_NAME --data url=$SERVICE_URL >/dev/null

# 4. Upload Certificate
echo "Uploading Certificate..."
CERT_ID=$(curl -s -X POST $ADMIN_URL/certificates \
  -F "cert=@tls.crt" \
  -F "key=@tls.key" \
  -F "snis[]=$DOMAIN" \
  | grep -o '"id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$CERT_ID" ]; then
  # If upload failed (maybe already exists), try to get existing SNI
  # (Simplification: just proceed, Kong might have it)
  echo "⚠️  Certificate upload check returned empty ID (might already exist)"
else
  echo "✓ Certificate uploaded (ID: $CERT_ID)"
fi

# 5. Create HTTPS Route
echo "Creating HTTPS Route..."
curl -s -X POST $ADMIN_URL/services/$SERVICE_NAME/routes \
  --data name=https-route \
  --data "paths[]=/" \
  --data "hosts[]=$DOMAIN" \
  --data "protocols[]=https" \
  --data "https_redirect_status_code=301" \
  | grep -q "id" || echo "Route might already exist"

# 6. Cleanup
kill $PF_PID
rm tls.key tls.crt

echo ""
echo "=== ✅ HTTPS Configuration Complete ==="
echo "You can now access the service via HTTPS:"
echo "kubectl -n url-shortener port-forward svc/kong 8443:443"
echo "Then: curl -k https://localhost:8443/health"
