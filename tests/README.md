# Testing Scripts

Comprehensive testing suite for URL Shortener service.

## Available Tests

### 1. System Test (`test.sh`)
Full integration test covering all endpoints and features.

```bash
./tests/test.sh
```

**Tests:**
- Service health checks
- URL shortening
- Redirects
- Statistics
- Custom aliases
- Deduplication
- Rate limiting
- Prometheus metrics
- Grafana availability

### 2. Latency Test - Bash (`latency-test.sh`)
Curl-based latency testing with multiple test modes.

```bash
# Quick test (10 iterations)
./tests/latency-test.sh quick

# Full test (100 iterations)
./tests/latency-test.sh full

# Redirect-only test (500 iterations)
./tests/latency-test.sh redirect

# Load test (requires 'hey' or 'wrk')
./tests/latency-test.sh load

# All tests
./tests/latency-test.sh all
```

### 3. Latency Test - Python (`latency_test.py`)
Async Python-based latency testing with detailed metrics.

```bash
# Quick test
python tests/latency_test.py --url http://localhost:8000 --test quick

# Full test
python tests/latency_test.py --test full --concurrency 10

# Load test (30s)
python tests/latency_test.py --test load --duration 30

# All tests
python tests/latency_test.py --test all --concurrency 20
```

**Requirements:**
```bash
pip install aiohttp
```

## Test Results

Results are saved to `test-results/` directory:
- `latency_YYYYMMDD_HHMMSS.csv` - Bash test results
- `latency_YYYYMMDD_HHMMSS.json` - Python test results
- `load_*.txt` - Load test results

## Metrics Measured

- **Min/Max/Avg latency**
- **P50, P95, P99 percentiles**
- **Success rate**
- **Requests per second (RPS)**
- **Cache hit vs miss performance**

## Prerequisites

**For bash tests:**
```bash
sudo apt install curl jq bc
```

**For load tests:**
```bash
# Option 1: hey
go install github.com/rakyll/hey@latest

# Option 2: wrk
sudo apt install wrk
```

**For Python tests:**
```bash
pip install aiohttp
```
