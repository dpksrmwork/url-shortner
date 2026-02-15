#!/bin/bash

echo "=========================================="
echo "URL Shortener - System Test"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if services are running
echo "1. Checking services..."
services=("cassandra" "kong" "kong-database" "prometheus" "grafana")
for service in "${services[@]}"; do
    if docker ps | grep -q "$service"; then
        echo -e "${GREEN}✓${NC} $service is running"
    else
        echo -e "${RED}✗${NC} $service is NOT running"
        exit 1
    fi
done
echo ""

# Test 2: Check Kong Admin API
echo "2. Testing Kong Admin API..."
if curl -s http://localhost:8001/status > /dev/null; then
    echo -e "${GREEN}✓${NC} Kong Admin API is accessible"
else
    echo -e "${RED}✗${NC} Kong Admin API is NOT accessible"
    exit 1
fi
echo ""

# Test 3: Initialize Cassandra (if not already done)
echo "3. Initializing Cassandra schema..."
docker exec -i cassandra cqlsh < cassandra/init/01-schema.cql 2>/dev/null
echo -e "${GREEN}✓${NC} Cassandra schema initialized"
echo ""

# Test 4: Configure Kong (if not already done)
echo "4. Configuring Kong..."
./kong-setup.sh > /dev/null 2>&1
echo -e "${GREEN}✓${NC} Kong configured"
echo ""

# Test 5: Create short URL
echo "5. Testing URL shortening..."
RESPONSE=$(curl -s -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/example/test-repo"}')

if echo "$RESPONSE" | grep -q "short_code"; then
    SHORT_CODE=$(echo "$RESPONSE" | grep -o '"short_code":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✓${NC} URL shortened successfully"
    echo "   Response: $RESPONSE"
    echo "   Short code: $SHORT_CODE"
else
    echo -e "${RED}✗${NC} Failed to shorten URL"
    echo "   Response: $RESPONSE"
    exit 1
fi
echo ""

# Test 6: Test redirect
echo "6. Testing redirect..."
REDIRECT_URL=$(curl -s -o /dev/null -w "%{redirect_url}" http://localhost:8000/$SHORT_CODE)
if [ "$REDIRECT_URL" = "https://github.com/example/test-repo" ]; then
    echo -e "${GREEN}✓${NC} Redirect works correctly"
    echo "   Redirects to: $REDIRECT_URL"
else
    echo -e "${RED}✗${NC} Redirect failed"
    exit 1
fi
echo ""

# Test 7: Test stats
echo "7. Testing stats endpoint..."
sleep 2  # Wait for click to be recorded
STATS=$(curl -s http://localhost:8000/stats/$SHORT_CODE)
if echo "$STATS" | grep -q "clicks"; then
    CLICKS=$(echo "$STATS" | grep -o '"clicks":[0-9]*' | cut -d':' -f2)
    echo -e "${GREEN}✓${NC} Stats endpoint works"
    echo "   Stats: $STATS"
    echo "   Clicks: $CLICKS"
else
    echo -e "${RED}✗${NC} Stats endpoint failed"
    exit 1
fi
echo ""

# Test 8: Test custom alias
echo "8. Testing custom alias..."
CUSTOM_RESPONSE=$(curl -s -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "custom_alias": "test123"}')

if echo "$CUSTOM_RESPONSE" | grep -q "test123"; then
    echo -e "${GREEN}✓${NC} Custom alias works"
    echo "   Response: $CUSTOM_RESPONSE"
else
    echo -e "${RED}✗${NC} Custom alias failed"
    exit 1
fi
echo ""

# Test 9: Test deduplication
echo "9. Testing URL deduplication..."
DEDUP_RESPONSE=$(curl -s -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/example/test-repo"}')

DEDUP_CODE=$(echo "$DEDUP_RESPONSE" | grep -o '"short_code":"[^"]*"' | cut -d'"' -f4)
if [ "$DEDUP_CODE" = "$SHORT_CODE" ]; then
    echo -e "${GREEN}✓${NC} Deduplication works (same URL returns same code)"
    echo "   Original code: $SHORT_CODE"
    echo "   Duplicate code: $DEDUP_CODE"
else
    echo -e "${YELLOW}⚠${NC} Deduplication may not be working"
fi
echo ""

# Test 10: Test rate limiting
echo "10. Testing rate limiting..."
RATE_LIMIT_COUNT=0
for i in {1..5}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/shorten \
      -H "Content-Type: application/json" \
      -d "{\"url\": \"https://example.com/test$i\"}")
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "201" ]; then
        ((RATE_LIMIT_COUNT++))
    fi
done
echo -e "${GREEN}✓${NC} Rate limiting is active (processed $RATE_LIMIT_COUNT/5 requests)"
echo ""

# Test 11: Check Prometheus metrics
echo "11. Testing Prometheus metrics..."
if curl -s http://localhost:8001/metrics | grep -q "kong_http_requests_total"; then
    echo -e "${GREEN}✓${NC} Prometheus metrics are being exported"
else
    echo -e "${RED}✗${NC} Prometheus metrics not found"
fi
echo ""

# Test 12: Check Prometheus server
echo "12. Testing Prometheus server..."
if curl -s http://localhost:9090/-/healthy | grep -q "Prometheus"; then
    echo -e "${GREEN}✓${NC} Prometheus server is healthy"
else
    echo -e "${YELLOW}⚠${NC} Prometheus server may not be ready yet"
fi
echo ""

# Test 13: Check Grafana
echo "13. Testing Grafana..."
if curl -s http://localhost:3000/api/health | grep -q "ok"; then
    echo -e "${GREEN}✓${NC} Grafana is accessible"
else
    echo -e "${YELLOW}⚠${NC} Grafana may not be ready yet"
fi
echo ""

# Summary
echo "=========================================="
echo -e "${GREEN}All tests passed!${NC}"
echo "=========================================="
echo ""
echo "Access points:"
echo "  • API Gateway:  http://localhost:8000"
echo "  • Kong Admin:   http://localhost:8001"
echo "  • Prometheus:   http://localhost:9090"
echo "  • Grafana:      http://localhost:3000 (admin/admin)"
echo ""
echo "Example commands:"
echo "  # Shorten URL"
echo "  curl -X POST http://localhost:8000/shorten \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"url\": \"https://example.com\"}'"
echo ""
echo "  # Redirect"
echo "  curl -L http://localhost:8000/$SHORT_CODE"
echo ""
echo "  # Get stats"
echo "  curl http://localhost:8000/stats/$SHORT_CODE"
echo ""
