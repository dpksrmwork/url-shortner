#!/bin/bash
# =============================================================================
# URL Shortener - Latency & Load Testing Script
# =============================================================================
# Usage:
#   ./latency-test.sh [test_type] [base_url]
#
# Examples:
#   ./latency-test.sh quick                    # Quick test against localhost
#   ./latency-test.sh full http://localhost:8000
#   ./latency-test.sh redirect http://my-k8s-ingress
# =============================================================================

set -e

# Configuration
BASE_URL="${2:-http://localhost:8000}"
TEST_TYPE="${1:-quick}"
RESULTS_DIR="./test-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  URL Shortener Latency Test${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Base URL: ${GREEN}${BASE_URL}${NC}"
echo -e "Test Type: ${GREEN}${TEST_TYPE}${NC}"
echo ""

# Create results directory
mkdir -p "$RESULTS_DIR"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"
    
    local missing=()
    
    command -v curl >/dev/null 2>&1 || missing+=("curl")
    command -v jq >/dev/null 2>&1 || missing+=("jq")
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}Missing required tools: ${missing[*]}${NC}"
        echo "Install with: sudo apt-get install ${missing[*]}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Core dependencies OK${NC}"
}

check_service_health() {
    echo -e "\n${YELLOW}Checking service health...${NC}"
    
    local health_response
    health_response=$(curl -s -w "\n%{http_code}" "${BASE_URL}/health" 2>/dev/null || echo "000")
    local http_code=$(echo "$health_response" | tail -1)
    local body=$(echo "$health_response" | head -1)
    
    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}✓ Service is healthy${NC}"
        echo "$body" | jq . 2>/dev/null || echo "$body"
    else
        echo -e "${RED}✗ Service unhealthy (HTTP $http_code)${NC}"
        echo -e "${RED}Make sure the service is running at ${BASE_URL}${NC}"
        exit 1
    fi
}

create_test_url() {
    echo -e "\n${YELLOW}Creating test URL...${NC}"
    
    local response
    response=$(curl -s -X POST "${BASE_URL}/shorten" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"https://example.com/test-$(date +%s)\"}")
    
    TEST_SHORT_CODE=$(echo "$response" | jq -r '.short_code')
    
    if [ "$TEST_SHORT_CODE" == "null" ] || [ -z "$TEST_SHORT_CODE" ]; then
        echo -e "${RED}Failed to create test URL${NC}"
        echo "$response"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Created short code: ${TEST_SHORT_CODE}${NC}"
}

# -----------------------------------------------------------------------------
# Latency Tests using curl
# -----------------------------------------------------------------------------

test_single_request() {
    local endpoint=$1
    local method=${2:-GET}
    local data=${3:-}
    
    local timing
    if [ "$method" == "POST" ]; then
        timing=$(curl -s -o /dev/null -w "%{time_namelookup},%{time_connect},%{time_appconnect},%{time_pretransfer},%{time_starttransfer},%{time_total}" \
            -X POST "${BASE_URL}${endpoint}" \
            -H "Content-Type: application/json" \
            -d "$data")
    else
        timing=$(curl -s -o /dev/null -w "%{time_namelookup},%{time_connect},%{time_appconnect},%{time_pretransfer},%{time_starttransfer},%{time_total}" \
            "${BASE_URL}${endpoint}")
    fi
    
    echo "$timing"
}

run_curl_latency_test() {
    local endpoint=$1
    local name=$2
    local iterations=${3:-100}
    local method=${4:-GET}
    local data=${5:-}
    
    echo -e "\n${BLUE}Testing: ${name}${NC}"
    echo "Endpoint: ${method} ${endpoint}"
    echo "Iterations: ${iterations}"
    
    local total=0
    local min=999999
    local max=0
    local results=()
    
    for i in $(seq 1 $iterations); do
        local timing=$(test_single_request "$endpoint" "$method" "$data")
        local total_time=$(echo "$timing" | cut -d',' -f6)
        local ms=$(echo "$total_time * 1000" | bc)
        
        results+=("$ms")
        total=$(echo "$total + $ms" | bc)
        
        if (( $(echo "$ms < $min" | bc -l) )); then min=$ms; fi
        if (( $(echo "$ms > $max" | bc -l) )); then max=$ms; fi
        
        # Progress indicator
        if [ $((i % 10)) -eq 0 ]; then
            echo -ne "\r  Progress: ${i}/${iterations}"
        fi
    done
    
    echo -ne "\r                              \r"
    
    # Calculate stats
    local avg=$(echo "scale=2; $total / $iterations" | bc)
    
    # Sort results for percentiles
    IFS=$'\n' sorted=($(sort -n <<<"${results[*]}")); unset IFS
    
    local p50_idx=$((iterations / 2))
    local p95_idx=$((iterations * 95 / 100))
    local p99_idx=$((iterations * 99 / 100))
    
    local p50=${sorted[$p50_idx]}
    local p95=${sorted[$p95_idx]}
    local p99=${sorted[$p99_idx]}
    
    echo -e "  ${GREEN}Results:${NC}"
    printf "    Min:    %8.2f ms\n" "$min"
    printf "    Max:    %8.2f ms\n" "$max"
    printf "    Avg:    %8.2f ms\n" "$avg"
    printf "    P50:    %8.2f ms\n" "$p50"
    printf "    P95:    %8.2f ms\n" "$p95"
    printf "    P99:    %8.2f ms\n" "$p99"
    
    # Save to file
    echo "${name},${min},${max},${avg},${p50},${p95},${p99}" >> "${RESULTS_DIR}/latency_${TIMESTAMP}.csv"
}

# -----------------------------------------------------------------------------
# Quick Test
# -----------------------------------------------------------------------------

run_quick_test() {
    echo -e "\n${YELLOW}Running quick latency test (10 iterations each)...${NC}"
    
    echo "Test,Min(ms),Max(ms),Avg(ms),P50(ms),P95(ms),P99(ms)" > "${RESULTS_DIR}/latency_${TIMESTAMP}.csv"
    
    # Health check
    run_curl_latency_test "/health" "Health Check" 10
    
    # Create URL
    run_curl_latency_test "/shorten" "Create URL" 10 "POST" '{"url": "https://example.com/quick-test"}'
    
    # Redirect (cache miss then hit)
    run_curl_latency_test "/${TEST_SHORT_CODE}" "Redirect" 10
    
    # Stats
    run_curl_latency_test "/stats/${TEST_SHORT_CODE}" "Get Stats" 10
    
    echo -e "\n${GREEN}Results saved to: ${RESULTS_DIR}/latency_${TIMESTAMP}.csv${NC}"
}

# -----------------------------------------------------------------------------
# Full Test
# -----------------------------------------------------------------------------

run_full_test() {
    echo -e "\n${YELLOW}Running full latency test (100 iterations each)...${NC}"
    
    echo "Test,Min(ms),Max(ms),Avg(ms),P50(ms),P95(ms),P99(ms)" > "${RESULTS_DIR}/latency_${TIMESTAMP}.csv"
    
    # Health check
    run_curl_latency_test "/health" "Health Check" 100
    
    # Create URL
    run_curl_latency_test "/shorten" "Create URL" 100 "POST" '{"url": "https://example.com/full-test"}'
    
    # Redirect - first request (cache miss)
    echo -e "\n${BLUE}Testing: Redirect (Cold - Cache Miss)${NC}"
    for i in {1..10}; do
        # Create new URL each time to force cache miss
        local response=$(curl -s -X POST "${BASE_URL}/shorten" \
            -H "Content-Type: application/json" \
            -d "{\"url\": \"https://example.com/cold-test-${i}-$(date +%s)\"}")
        local code=$(echo "$response" | jq -r '.short_code')
        test_single_request "/${code}" "GET" | cut -d',' -f6
    done
    
    # Redirect - warm (cache hit)
    run_curl_latency_test "/${TEST_SHORT_CODE}" "Redirect (Warm - Cache Hit)" 100
    
    # Stats
    run_curl_latency_test "/stats/${TEST_SHORT_CODE}" "Get Stats" 100
    
    echo -e "\n${GREEN}Results saved to: ${RESULTS_DIR}/latency_${TIMESTAMP}.csv${NC}"
}

# -----------------------------------------------------------------------------
# Redirect-only Test (for measuring cache performance)
# -----------------------------------------------------------------------------

run_redirect_test() {
    echo -e "\n${YELLOW}Running redirect latency test (500 iterations)...${NC}"
    
    echo "Test,Min(ms),Max(ms),Avg(ms),P50(ms),P95(ms),P99(ms)" > "${RESULTS_DIR}/latency_${TIMESTAMP}.csv"
    
    # Warm up cache
    echo "Warming up cache..."
    for i in {1..10}; do
        curl -s -o /dev/null "${BASE_URL}/${TEST_SHORT_CODE}"
    done
    
    # Test cached redirects
    run_curl_latency_test "/${TEST_SHORT_CODE}" "Redirect (Cached)" 500
    
    echo -e "\n${GREEN}Results saved to: ${RESULTS_DIR}/latency_${TIMESTAMP}.csv${NC}"
}

# -----------------------------------------------------------------------------
# Load Test (requires 'hey' or 'wrk')
# -----------------------------------------------------------------------------

run_load_test() {
    echo -e "\n${YELLOW}Running load test...${NC}"
    
    if command -v hey >/dev/null 2>&1; then
        echo -e "${GREEN}Using 'hey' for load testing${NC}"
        
        echo -e "\n${BLUE}Load Test: Redirect endpoint${NC}"
        echo "Concurrency: 50, Duration: 30s"
        hey -z 30s -c 50 "${BASE_URL}/${TEST_SHORT_CODE}" | tee "${RESULTS_DIR}/load_redirect_${TIMESTAMP}.txt"
        
        echo -e "\n${BLUE}Load Test: Create endpoint${NC}"
        echo "Concurrency: 10, Requests: 1000"
        hey -n 1000 -c 10 -m POST \
            -H "Content-Type: application/json" \
            -d '{"url": "https://example.com/load-test"}' \
            "${BASE_URL}/shorten" | tee "${RESULTS_DIR}/load_create_${TIMESTAMP}.txt"
            
    elif command -v wrk >/dev/null 2>&1; then
        echo -e "${GREEN}Using 'wrk' for load testing${NC}"
        
        echo -e "\n${BLUE}Load Test: Redirect endpoint${NC}"
        wrk -t4 -c50 -d30s "${BASE_URL}/${TEST_SHORT_CODE}" | tee "${RESULTS_DIR}/load_redirect_${TIMESTAMP}.txt"
        
    else
        echo -e "${RED}Neither 'hey' nor 'wrk' found.${NC}"
        echo "Install one of these for load testing:"
        echo "  hey: go install github.com/rakyll/hey@latest"
        echo "  wrk: sudo apt-get install wrk"
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    check_dependencies
    check_service_health
    create_test_url
    
    case $TEST_TYPE in
        quick)
            run_quick_test
            ;;
        full)
            run_full_test
            ;;
        redirect)
            run_redirect_test
            ;;
        load)
            run_load_test
            ;;
        all)
            run_full_test
            run_load_test
            ;;
        *)
            echo -e "${RED}Unknown test type: ${TEST_TYPE}${NC}"
            echo "Available types: quick, full, redirect, load, all"
            exit 1
            ;;
    esac
    
    echo -e "\n${GREEN}============================================${NC}"
    echo -e "${GREEN}  Testing Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
}

main
