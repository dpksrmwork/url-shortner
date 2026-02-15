# Postman Collection - URL Shortener

## Import to Postman

1. Open Postman
2. Click **Import** button
3. Select `postman-collection.json`
4. Select `postman-environment.json`
5. Select the environment from dropdown

## Collection Structure

### 1. URL Operations
- **Shorten URL** - Create short URL with auto-generated code
- **Shorten URL with Custom Alias** - Create with custom alias and TTL
- **Redirect to Long URL** - Test 301 redirect
- **Get URL Statistics** - View click counts and metadata

### 2. Kong Admin API
- **Kong Status** - Check gateway health
- **List Services** - View configured services
- **List Routes** - View routing rules
- **List Plugins** - View active plugins
- **Prometheus Metrics** - Get Kong metrics

### 3. Monitoring
- **Prometheus Health** - Check Prometheus status
- **Prometheus Targets** - View scrape targets
- **Query Request Rate** - Example PromQL query
- **Grafana Health** - Check Grafana status

### 4. Test Scenarios
- **Bulk Create URLs** - Load testing (use Collection Runner)
- **Test Rate Limiting** - Trigger rate limits
- **Test Deduplication** - Verify same URL returns same code

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `base_url` | http://localhost:8000 | API Gateway endpoint |
| `kong_admin_url` | http://localhost:8001 | Kong Admin API |
| `prometheus_url` | http://localhost:9090 | Prometheus server |
| `grafana_url` | http://localhost:3000 | Grafana dashboard |
| `short_code` | (empty) | Store short code from responses |

## Usage

### Basic Flow

1. **Create Short URL**
   - Run "Shorten URL" request
   - Copy `short_code` from response
   - Set it in environment variable

2. **Test Redirect**
   - Run "Redirect to Long URL"
   - Should return 301 redirect

3. **Check Stats**
   - Run "Get URL Statistics"
   - View click count

### Load Testing

1. Select "Bulk Create URLs" request
2. Click **Runner** button
3. Set iterations (e.g., 100)
4. Run collection
5. Check Prometheus metrics

### Rate Limiting Test

1. Select "Test Rate Limiting"
2. Click **Runner**
3. Set iterations to 150 (exceeds 100/min limit)
4. Observe 429 errors after limit

## Kubernetes Setup

If using Kubernetes, first start port-forwards:

```bash
kubectl port-forward svc/kong -n url-shortener 8000:8000 8001:8001 &
kubectl port-forward svc/prometheus -n url-shortener 9090:9090 &
kubectl port-forward svc/grafana -n url-shortener 3000:3000 &
```

Or use the helper script:
```bash
./k8s-access.sh
```

## Docker Compose Setup

If using Docker Compose:

```bash
make docker-up
make cassandra-init
make kong-setup
```

Services will be available at default ports.

## Example Requests

### Create Short URL
```bash
POST http://localhost:8000/shorten
Content-Type: application/json

{
  "url": "https://github.com/kubernetes/kubernetes"
}
```

### With Custom Alias
```bash
POST http://localhost:8000/shorten
Content-Type: application/json

{
  "url": "https://kubernetes.io",
  "custom_alias": "k8s",
  "user_id": "user123",
  "ttl_days": 365
}
```

### Get Statistics
```bash
GET http://localhost:8000/stats/k8s
```

## Response Examples

### Shorten URL Response
```json
{
  "short_code": "3Vu2t62x",
  "short_url": "http://localhost:8000/3Vu2t62x",
  "long_url": "https://github.com/kubernetes/kubernetes"
}
```

### Statistics Response
```json
{
  "short_code": "3Vu2t62x",
  "long_url": "https://github.com/kubernetes/kubernetes",
  "clicks": 42,
  "expires_at": "2029-02-05T17:43:30.050000"
}
```

## Troubleshooting

**Connection Refused:**
- Ensure services are running
- Check port-forwards are active
- Verify environment variables

**404 Not Found:**
- Check Kong routes are configured
- Run `make kong-setup`
- Verify service is healthy

**Rate Limit Errors (429):**
- Expected behavior after 100 requests/minute
- Wait 1 minute or adjust Kong plugin settings

## Advanced Usage

### Collection Runner

1. Click **Runner** button
2. Select collection or folder
3. Set iterations and delay
4. Add data file (CSV) for parameterized testing
5. Run and view results

### Pre-request Scripts

Add to request to auto-extract short_code:

```javascript
pm.test("Extract short_code", function() {
    var jsonData = pm.response.json();
    pm.environment.set("short_code", jsonData.short_code);
});
```

### Tests

Add assertions:

```javascript
pm.test("Status code is 200", function() {
    pm.response.to.have.status(200);
});

pm.test("Response has short_code", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('short_code');
});
```
