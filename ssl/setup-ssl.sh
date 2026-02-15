#!/bin/bash

echo "🔐 SSL Setup for URL Shortener"
echo "================================"

# Create certs directory
mkdir -p ssl/certs

# Generate self-signed certificate
echo "Generating self-signed certificate..."
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ssl/certs/key.pem \
  -out ssl/certs/cert.pem \
  -days 365 \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

echo "✅ Certificate generated in ./ssl/certs/"
echo ""
echo "Usage:"
echo "  Development: make run-ssl"
echo "  Production:  docker compose up -d"
echo ""
echo "Access URLs:"
echo "  HTTPS: https://localhost:8443 (dev) or https://localhost (docker)"
echo "  HTTP:  http://localhost (redirects to HTTPS)"
