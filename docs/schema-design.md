# Database Schema Design - URL Shortener

## Overview

This schema is designed to support:
- **Billions of URLs** with efficient storage
- **High read throughput** (200K TPS peak)
- **Low latency redirects** (<100ms)
- **Analytics tracking** (non-real-time)
- **Deduplication** (1-to-1 long URL → short URL mapping)

---

## Database Choice Rationale

| Requirement | Recommended DB | Reasoning |
|-------------|---------------|-----------|
| URL Mapping | **Cassandra / DynamoDB** | High availability, partition tolerance, fast reads by key |
| Analytics | **ClickHouse / TimescaleDB** | Optimized for time-series analytics, aggregations |
| Deduplication Cache | **Redis** | Fast hash lookups for URL deduplication |
| Rate Limiting | **Redis** | In-memory counters with TTL |

---

## Core Tables

### 1. `urls` - Primary URL Mapping Table

This is the **hot path** table for redirects. Optimized for reads by short_code.

```sql
CREATE TABLE urls (
    -- Primary identifier
    short_code      VARCHAR(10) PRIMARY KEY,  -- Base62 encoded, 6-8 chars typical
    
    -- URL data
    long_url        TEXT NOT NULL,            -- Original URL (up to 2KB)
    long_url_hash   CHAR(64) NOT NULL,        -- SHA-256 hash for deduplication
    
    -- Metadata
    user_id         UUID,                      -- NULL for anonymous
    is_custom_alias BOOLEAN DEFAULT FALSE,    -- User-defined vs auto-generated
    
    -- Lifecycle
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP,                 -- NULL = never expires
    is_active       BOOLEAN DEFAULT TRUE,     -- Soft delete / deactivation
    
    -- Counters (denormalized for fast reads)
    click_count     BIGINT DEFAULT 0,         -- Approximate, updated periodically
    
    -- Indexes for deduplication
    INDEX idx_long_url_hash (long_url_hash),
    INDEX idx_user_id (user_id),
    INDEX idx_expires_at (expires_at) WHERE is_active = TRUE
);
```

**Key Design Decisions:**
- `short_code` as primary key for O(1) redirect lookups
- `long_url_hash` enables deduplication without full URL comparison
- `click_count` denormalized to avoid JOIN on redirects
- Partial index on `expires_at` for efficient TTL cleanup

---

### 2. `url_dedup` - Deduplication Lookup Table

Enables finding existing short_code for a given long URL (1-to-1 mapping requirement).

```sql
CREATE TABLE url_dedup (
    long_url_hash   CHAR(64) PRIMARY KEY,     -- SHA-256 of long_url
    short_code      VARCHAR(10) NOT NULL,     -- Reference to urls table
    created_at      TIMESTAMP DEFAULT NOW(),
    
    FOREIGN KEY (short_code) REFERENCES urls(short_code)
);
```

**Usage Flow:**
1. Hash incoming long_url
2. Check `url_dedup` for existing mapping
3. If exists → return existing short_code
4. If not → generate new short_code, insert into both tables

---

### 3. `url_analytics` - Click Event Log (Append-Only)

High-volume write table for analytics. Non-real-time processing acceptable.

```sql
CREATE TABLE url_analytics (
    id              UUID PRIMARY KEY,          -- Or use ULID for time-ordering
    short_code      VARCHAR(10) NOT NULL,
    
    -- Event data
    clicked_at      TIMESTAMP DEFAULT NOW(),
    
    -- Client information
    ip_address      INET,                      -- For geo lookup (anonymize later)
    user_agent      TEXT,
    referer         TEXT,
    
    -- Derived fields (populated by async processor)
    country_code    CHAR(2),
    city            VARCHAR(100),
    device_type     VARCHAR(20),               -- mobile, desktop, tablet
    browser         VARCHAR(50),
    os              VARCHAR(50),
    
    -- Partitioning key
    event_date      DATE DEFAULT CURRENT_DATE
) PARTITION BY RANGE (event_date);

-- Create monthly partitions
CREATE TABLE url_analytics_2026_01 PARTITION OF url_analytics
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
    
CREATE TABLE url_analytics_2026_02 PARTITION OF url_analytics
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

**Design Decisions:**
- Partitioned by date for efficient time-range queries and data retention
- Append-only for high write throughput
- Derived fields populated async (user_agent parsing, geo-IP lookup)

---

### 4. `url_analytics_daily` - Pre-Aggregated Analytics

Materialized view or separate table for fast dashboard queries.

```sql
CREATE TABLE url_analytics_daily (
    short_code      VARCHAR(10),
    event_date      DATE,
    
    -- Aggregated metrics
    total_clicks    BIGINT DEFAULT 0,
    unique_ips      BIGINT DEFAULT 0,          -- Approximate using HyperLogLog
    
    -- Top dimensions (JSONB for flexibility)
    top_countries   JSONB,                     -- [{"US": 1000}, {"IN": 500}]
    top_referers    JSONB,
    device_breakdown JSONB,                    -- {"mobile": 60, "desktop": 35, "tablet": 5}
    
    -- Hourly distribution
    hourly_clicks   INT[24],                   -- Array of 24 hourly counts
    
    PRIMARY KEY (short_code, event_date)
);

-- Index for user dashboard queries
CREATE INDEX idx_analytics_daily_user ON url_analytics_daily(short_code, event_date DESC);
```

---

### 5. `users` - User Management (Optional)

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255),              -- Argon2/bcrypt
    
    -- Account status
    created_at      TIMESTAMP DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    
    -- Rate limiting
    tier            VARCHAR(20) DEFAULT 'free', -- free, pro, enterprise
    api_key         VARCHAR(64) UNIQUE,
    
    -- Quotas
    monthly_url_limit   INT DEFAULT 1000,
    monthly_urls_created INT DEFAULT 0,
    quota_reset_at      TIMESTAMP
);
```

---

### 6. `blocked_urls` - Security/Spam Protection

```sql
CREATE TABLE blocked_urls (
    id              SERIAL PRIMARY KEY,
    pattern         TEXT NOT NULL,             -- URL pattern or domain
    pattern_type    VARCHAR(20) NOT NULL,      -- 'exact', 'domain', 'regex'
    reason          VARCHAR(100),              -- 'malware', 'phishing', 'spam'
    
    created_at      TIMESTAMP DEFAULT NOW(),
    created_by      UUID,                       -- Admin user
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_blocked_pattern ON blocked_urls(pattern) WHERE is_active = TRUE;
```

---

## Redis Data Structures

### Rate Limiting
```
rate_limit:{user_id}:{minute} → count (TTL: 60s)
rate_limit:{ip}:{minute} → count (TTL: 60s)
```

### URL Cache (Hot URLs)
```
url:{short_code} → {long_url, expires_at} (TTL: 1 hour or until expiry)
```

### Dedup Cache
```
dedup:{url_hash} → short_code (TTL: 24 hours)
```

### Short Code Generation (Distributed Counter)
```
short_code_counter → INCR (atomic counter for ID generation)
```

---

## Entity Relationship Diagram

```
┌─────────────┐       ┌──────────────────┐
│   users     │       │  blocked_urls    │
│─────────────│       │──────────────────│
│ id (PK)     │       │ id (PK)          │
│ email       │       │ pattern          │
│ tier        │       │ pattern_type     │
│ api_key     │       │ reason           │
└──────┬──────┘       └──────────────────┘
       │
       │ 1:N
       ▼
┌──────────────┐       ┌──────────────────┐
│    urls      │◄──────│   url_dedup      │
│──────────────│       │──────────────────│
│ short_code   │       │ long_url_hash(PK)│
│ (PK)         │       │ short_code (FK)  │
│ long_url     │       └──────────────────┘
│ long_url_hash│
│ user_id (FK) │
│ expires_at   │
│ click_count  │
└──────┬───────┘
       │
       │ 1:N
       ▼
┌───────────────────┐      ┌─────────────────────────┐
│  url_analytics    │─────►│  url_analytics_daily    │
│───────────────────│      │─────────────────────────│
│ id (PK)           │      │ short_code, date (PK)   │
│ short_code        │      │ total_clicks            │
│ clicked_at        │      │ unique_ips              │
│ ip_address        │      │ top_countries (JSONB)   │
│ country_code      │      └─────────────────────────┘
│ device_type       │            (Aggregated View)
└───────────────────┘
   (Partitioned by date)
```

---

## Indexes Summary

| Table | Index | Purpose |
|-------|-------|---------|
| `urls` | `PRIMARY KEY (short_code)` | O(1) redirect lookup |
| `urls` | `idx_long_url_hash` | Deduplication |
| `urls` | `idx_user_id` | User's URLs listing |
| `urls` | `idx_expires_at` (partial) | TTL cleanup batch job |
| `url_dedup` | `PRIMARY KEY (long_url_hash)` | Fast dedup check |
| `url_analytics` | Partition by `event_date` | Time-range queries |
| `url_analytics_daily` | `(short_code, event_date DESC)` | Dashboard queries |

---

## Data Flow Diagrams

### URL Creation Flow
```
1. Client → POST /shorten {long_url}
2. Hash long_url → SHA-256
3. Check Redis dedup cache
   └─ HIT → Return existing short_code
4. Check url_dedup table
   └─ HIT → Cache in Redis, return short_code
5. Check blocked_urls for malware/spam
6. Generate new short_code (Base62 counter)
7. INSERT into urls + url_dedup (transaction)
8. Cache in Redis
9. Return short_code
```

### Redirect Flow (Optimized for <100ms)
```
1. Client → GET /{short_code}
2. Check Redis cache
   └─ HIT → 302 Redirect + async log click
3. Query urls table by short_code
   └─ NOT FOUND → 404
   └─ EXPIRED → 410 Gone
4. Cache in Redis (1 hour TTL)
5. 302 Redirect to long_url
6. Async: INSERT into url_analytics (fire-and-forget)
```

---

## Storage Estimation Validation

Based on your capacity estimates (1B URLs/month, 3 years):

| Table | Row Size | Rows (3 years) | Storage |
|-------|----------|----------------|---------|
| `urls` | ~1 KB | 36 Billion | ~36 TB |
| `url_dedup` | ~100 bytes | 36 Billion | ~3.6 TB |
| `url_analytics` | ~200 bytes | 36T clicks* | ~7.2 PB |
| `url_analytics_daily` | ~1 KB | 36B × 365 days | ~13 TB |

*Assuming 100:1 read ratio, analytics can be sampled (1% sampling = ~72 TB)

**Total Primary Storage: ~40 TB** (excluding analytics raw logs)
**With 3x Replication: ~120 TB** ✓ Matches your 108TB estimate

---

## Next Steps

1. **Short Code Generation Strategy** - Define Base62 encoding approach
2. **Caching Strategy** - Redis architecture for hot URLs
3. **Sharding Strategy** - Consistent hashing for horizontal scaling
4. **Analytics Pipeline** - Kafka → Flink → ClickHouse for real-time-ish analytics
