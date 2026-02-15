# URL Shortener

High-performance URL shortening service built with FastAPI and Apache Cassandra.

## Features

- ✅ Shorten long URLs to compact codes
- ✅ Custom aliases support
- ✅ URL deduplication (same URL → same short code)
- ✅ Configurable TTL/expiration
- ✅ Click tracking and analytics
- ✅ 301 redirects for SEO
- ✅ High availability with Cassandra

## Architecture

```
FastAPI (Python) → Cassandra (NoSQL)
```

**Tech Stack:**
- **API**: FastAPI + Uvicorn
- **Database**: Apache Cassandra 4.1
- **Language**: Python 3.13

## Project Structure

See [STRUCTURE.md](STRUCTURE.md) for detailed project organization.

## Quick Start

### 1. Start Cassandra

```bash
make cassandra-up
make cassandra-init
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
make install
```

### 3. Run Application

```bash
make run
```

API available at: http://localhost:8000

## API Documentation

### Create Short URL

```bash
POST /shorten
Content-Type: application/json

{
  "url": "https://example.com/very/long/url",
  "custom_alias": "mylink",      # Optional
  "user_id": "user123",           # Optional
  "ttl_days": 365                 # Optional, default 1095 (3 years)
}
```

**Response:**
```json
{
  "short_code": "mylink",
  "short_url": "http://localhost:8000/mylink",
  "long_url": "https://example.com/very/long/url"
}
```

### Redirect to Original URL

```bash
GET /{short_code}
```

Returns 301 redirect to original URL and increments click counter.

### Get URL Statistics

```bash
GET /stats/{short_code}
```

**Response:**
```json
{
  "short_code": "mylink",
  "long_url": "https://example.com/very/long/url",
  "clicks": 42,
  "expires_at": "2026-01-15T10:30:00"
}
```

## Examples

```bash
# Shorten URL
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/example/repo"}'

# Custom alias
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "custom_alias": "ex"}'

# Redirect
curl -L http://localhost:8000/ex

# Get stats
curl http://localhost:8000/stats/ex
```

## Database Schema

### Tables

**urls** - Main URL storage
- `short_code` (PK): Unique identifier
- `long_url`: Original URL
- `created_at`: Creation timestamp
- `expires_at`: Expiration timestamp
- `user_id`: Optional user identifier

**url_clicks** - Click counters
- `short_code` (PK)
- `click_count`: Counter column

**url_dedup** - Deduplication index
- `url_hash` (PK): SHA-256 hash of long URL
- `short_code`: Associated short code

## Configuration

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

Key variables:
- `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `KONG_PG_PASSWORD`, `GF_SECURITY_ADMIN_PASSWORD`
- `BASE_URL`

## Development

```bash
# Start Cassandra
make cassandra-up

# Initialize schema
make cassandra-init

# Access CQL shell
make cassandra-shell

# Check cluster status
make cassandra-status

# Run application
make run

# Stop Cassandra
make cassandra-down
```

## Capacity Planning

Based on requirements:
- **Storage**: 36TB for 1B URLs/month over 3 years
- **Write TPS**: 400 (peak: 2000)
- **Read TPS**: 40,000 (peak: 200,000)
- **Read:Write Ratio**: 100:1

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed capacity planning.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and design
- [docs/SECURITY.md](docs/SECURITY.md) - Security features
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide

## License

MIT
