# Security Documentation - URL Shortener

## Overview

This document describes the security measures implemented in the URL shortener service.

## Security Features Implemented

### 1. Input Validation

#### URL Validation (`app/core/security.py`)
- Scheme validation (only http/https allowed)
- Blocks dangerous patterns (javascript:, data:, vbscript:, file:)
- Blocks suspicious TLDs (.tk, .ml, .ga, .cf, .gq)
- Blocks IP-based URLs
- URL length limit (2048 characters)
- Domain blocklist support

#### Custom Alias Validation (`app/models/schemas.py`)
- Length: 3-30 characters
- Pattern: alphanumeric, hyphens, underscores only
- Must start with letter or number
- Blocks reserved words (health, stats, admin, etc.)
- Blocks path traversal attempts (../, /, \)

### 2. Rate Limiting (`app/middleware/rate_limit.py`)

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /shorten | 100 | 60s |
| GET /{code} | 1000 | 60s |
| GET /stats/* | 200 | 60s |
| Default | 500 | 60s |

Features:
- Sliding window algorithm
- Redis-backed (distributed)
- In-memory fallback
- X-RateLimit headers
- 429 response with Retry-After

### 3. Security Headers (`app/middleware/security_headers.py`)

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'; ...
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 4. Container Security (`Dockerfile`)

- Non-root user execution
- Minimal base image (python:slim)
- No unnecessary packages
- Health check included

### 5. Short Code Generation

- Uses SHA-256 + random bytes (secrets.token_bytes)
- Prevents enumeration attacks
- Collision detection with regeneration

## Security Checklist

### Implemented ✅
- [x] Input validation (URL and alias)
- [x] Rate limiting middleware
- [x] Security headers
- [x] Non-root container
- [x] Reserved word blocking
- [x] Path traversal prevention
- [x] URL scheme validation
- [x] Domain blocklist structure
- [x] Short code validation

### Recommended for Production ⚠️
- [ ] Enable HTTPS/TLS (via ingress or Kong)
- [ ] Enable HSTS header
- [ ] Disable /docs endpoint
- [ ] Add authentication (API keys or OAuth)
- [ ] Integrate with threat intelligence (Google Safe Browsing)
- [ ] Add audit logging
- [ ] Enable Kubernetes NetworkPolicy
- [ ] Use Kubernetes Secrets for credentials
- [ ] Enable Pod Security Standards
- [ ] Regular security scanning (Trivy, Snyk)

## Configuration

### Environment Variables

```env
# Enable HSTS (only with HTTPS)
ENABLE_HSTS=false

# Rate limiting
RATE_LIMIT_CREATE=100
RATE_LIMIT_REDIRECT=1000

# Blocklist file path
BLOCKLIST_PATH=/app/config/blocklist.txt
```

### Kubernetes Security Context

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
```

## Testing Security

```bash
# Test rate limiting
for i in {1..150}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/shorten -H "Content-Type: application/json" -d '{"url":"https://example.com"}'; done

# Test reserved word blocking
curl -X POST http://localhost:8000/shorten -H "Content-Type: application/json" -d '{"url":"https://example.com","custom_alias":"admin"}'
# Expected: 400 Bad Request

# Test path traversal
curl -X POST http://localhost:8000/shorten -H "Content-Type: application/json" -d '{"url":"https://example.com","custom_alias":"../etc"}'
# Expected: 400 Bad Request

# Test invalid scheme
curl -X POST http://localhost:8000/shorten -H "Content-Type: application/json" -d '{"url":"javascript:alert(1)"}'
# Expected: 422 Unprocessable Entity
```

## Incident Response

If you discover a security vulnerability:
1. Check rate limit headers to identify abuse
2. Review application logs for suspicious patterns
3. Add offending domains to blocklist
4. Update rate limits if needed

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE-601: Open Redirect](https://cwe.mitre.org/data/definitions/601.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
