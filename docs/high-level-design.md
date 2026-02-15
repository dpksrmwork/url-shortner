# High-Level Design - URL Shortener

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Primary Datastore** | Apache Cassandra | URL storage, high availability, horizontal scaling |
| **Cache Layer** | Redis Cluster | Hot URL caching, rate limiting, distributed counters |
| **Analytics Engine** | ClickHouse | Time-series analytics, aggregations, dashboards |
| **Message Queue** | Apache Kafka | Async click event streaming |
| **API Gateway** | Kong / NGINX | Rate limiting, SSL termination, routing |
| **Application** | Go / Node.js | Stateless API servers |

---

## System Architecture

```
                                    ┌─────────────────────────────────────────────────────────────────┐
                                    │                         CDN (CloudFlare)                        │
                                    │              - Edge caching for popular short URLs               │
                                    │              - DDoS protection                                   │
                                    └─────────────────────────────┬───────────────────────────────────┘
                                                                  │
                                                                  ▼
                                    ┌─────────────────────────────────────────────────────────────────┐
                                    │                      Load Balancer (L7)                         │
                                    │                    - Health checks                               │
                                    │                    - SSL termination                             │
                                    └─────────────────────────────┬───────────────────────────────────┘
                                                                  │
                         ┌────────────────────────────────────────┼────────────────────────────────────────┐
                         │                                        │                                        │
                         ▼                                        ▼                                        ▼
              ┌─────────────────────┐                ┌─────────────────────┐                ┌─────────────────────┐
              │   API Server #1     │                │   API Server #2     │                │   API Server #N     │
              │   (Stateless)       │                │   (Stateless)       │                │   (Stateless)       │
              │                     │                │                     │                │                     │
              │ - URL Creation      │                │ - URL Creation      │                │ - URL Creation      │
              │ - URL Redirect      │                │ - URL Redirect      │                │ - URL Redirect      │
              │ - Analytics API     │                │ - Analytics API     │                │ - Analytics API     │
              └─────────┬───────────┘                └─────────┬───────────┘                └─────────┬───────────┘
                        │                                      │                                      │
                        └──────────────────────────────────────┼──────────────────────────────────────┘
                                                               │
                    ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
                    │                                          │                                          │
                    ▼                                          ▼                                          ▼
    ┌───────────────────────────────┐          ┌───────────────────────────────┐          ┌───────────────────────────┐
    │        Redis Cluster          │          │       Cassandra Cluster       │          │          Kafka            │
    │                               │          │                               │          │                           │
    │  ┌─────────────────────────┐  │          │  ┌─────────────────────────┐  │          │  ┌─────────────────────┐  │
    │  │   URL Cache             │  │          │  │   urls table            │  │          │  │  click_events       │  │
    │  │   short_code → long_url │  │          │  │   (short_code → data)   │  │          │  │  topic              │  │
    │  └─────────────────────────┘  │          │  └─────────────────────────┘  │          │  └──────────┬──────────┘  │
    │  ┌─────────────────────────┐  │          │  ┌─────────────────────────┐  │          │             │             │
    │  │   Dedup Cache           │  │          │  │   url_dedup table       │  │          │             ▼             │
    │  │   url_hash → short_code │  │          │  │   (hash → short_code)   │  │          │  ┌─────────────────────┐  │
    │  └─────────────────────────┘  │          │  └─────────────────────────┘  │          │  │  Kafka Consumer     │  │
    │  ┌─────────────────────────┐  │          │  ┌─────────────────────────┐  │          │  │  (Batch Insert)     │  │
    │  │   Rate Limiter          │  │          │  │   users table           │  │          │  └──────────┬──────────┘  │
    │  │   Sliding window        │  │          │  └─────────────────────────┘  │          │             │             │
    │  └─────────────────────────┘  │          │                               │          └─────────────┼─────────────┘
    │  ┌─────────────────────────┐  │          │  RF=3, CL=QUORUM             │                        │
    │  │   ID Generator          │  │          │                               │                        │
    │  │   Atomic counter        │  │          └───────────────────────────────┘                        │
    │  └─────────────────────────┘  │                                                                   │
    │                               │                                                                   │
    │  6 nodes (3 masters,          │                                                                   │
    │  3 replicas)                  │                                                                   ▼
    └───────────────────────────────┘                                              ┌───────────────────────────────────┐
                                                                                   │         ClickHouse Cluster        │
                                                                                   │                                   │
                                                                                   │   ┌───────────────────────────┐   │
                                                                                   │   │   url_clicks table        │   │
                                                                                   │   │   (Partitioned by day)    │   │
                                                                                   │   └───────────────────────────┘   │
                                                                                   │   ┌───────────────────────────┐   │
                                                                                   │   │   url_analytics_mv        │   │
                                                                                   │   │   (Materialized View)     │   │
                                                                                   │   └───────────────────────────┘   │
                                                                                   │                                   │
                                                                                   │   3 shards × 2 replicas           │
                                                                                   └───────────────────────────────────┘
```

---

## Component Deep Dive

### 1. API Servers (Stateless)

**Responsibilities:**
- Handle HTTP requests for URL creation and redirection
- Validate inputs, check blocklists
- Orchestrate reads/writes across Redis and Cassandra

**Scaling Strategy:**
- Horizontal scaling behind load balancer
- Auto-scale based on CPU/request latency
- Target: 50-100 instances for 200K TPS peak

```
┌────────────────────────────────────────────────────────────────┐
│                        API Server                              │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  /shorten    │  │  /{code}     │  │  /analytics/{code}   │  │
│  │  POST        │  │  GET         │  │  GET                 │  │
│  │              │  │              │  │                      │  │
│  │  Create URL  │  │  Redirect    │  │  Get stats           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Service Layer                         │   │
│  │  - URL Validation    - Blocklist Check                   │   │
│  │  - Deduplication     - Short Code Generation             │   │
│  │  - Cache Management  - Analytics Aggregation             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Redis Client│  │Cassandra    │  │ Kafka       │            │
│  │             │  │Driver       │  │ Producer    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└────────────────────────────────────────────────────────────────┘
```

---

### 2. Redis Cluster Architecture

**Cluster Configuration:**
- 6 nodes: 3 masters + 3 replicas
- 16,384 hash slots distributed across masters
- Automatic failover with Redis Sentinel

**Data Structures:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      Redis Cluster                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. URL CACHE (String)                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Key:    url:{short_code}                                │    │
│  │  Value:  {long_url}                                      │    │
│  │  TTL:    3600 seconds (1 hour) or until URL expiry       │    │
│  │                                                          │    │
│  │  Example: url:abc123 → "https://example.com/very/long"   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  2. DEDUP CACHE (String)                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Key:    dedup:{sha256_hash}                             │    │
│  │  Value:  {short_code}                                    │    │
│  │  TTL:    86400 seconds (24 hours)                        │    │
│  │                                                          │    │
│  │  Example: dedup:a1b2c3... → "abc123"                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  3. RATE LIMITER (Sorted Set - Sliding Window)                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Key:    ratelimit:{user_id}:create                      │    │
│  │  Members: {timestamp}:{request_id}                       │    │
│  │  Score:  timestamp                                       │    │
│  │  TTL:    60 seconds (window size)                        │    │
│  │                                                          │    │
│  │  Algorithm: ZREMRANGEBYSCORE + ZCARD + ZADD              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  4. ID GENERATOR (Atomic Counter)                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Key:    shortcode:counter                               │    │
│  │  Value:  INCR → Base62 encode                            │    │
│  │                                                          │    │
│  │  Alternative: Pre-allocated ranges per API server        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  5. BLOCKLIST CACHE (Set)                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Key:    blocklist:domains                               │    │
│  │  Members: blocked domain hashes                          │    │
│  │  TTL:    3600 seconds, refreshed by background job       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Cache Strategy:**
- **Write-through** for URL creation
- **Cache-aside** for redirects (read from cache, fallback to Cassandra)
- **TTL-based eviction** for memory management

---

### 3. Cassandra Cluster Architecture

**Cluster Configuration:**
- 9-12 nodes across 3 datacenters (for geo-distribution)
- Replication Factor: 3 (one replica per DC)
- Consistency Level: LOCAL_QUORUM for writes, LOCAL_ONE for reads

**Keyspace & Tables:**

```cql
-- Keyspace with NetworkTopologyStrategy for multi-DC
CREATE KEYSPACE url_shortener
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3,
    'dc3': 3
};

USE url_shortener;
```

#### Table: `urls` (Primary URL Storage)

```cql
CREATE TABLE urls (
    short_code      TEXT,
    long_url        TEXT,
    long_url_hash   TEXT,
    user_id         UUID,
    is_custom       BOOLEAN,
    created_at      TIMESTAMP,
    expires_at      TIMESTAMP,
    click_count     COUNTER,      -- Separate counter table needed
    
    PRIMARY KEY (short_code)
) WITH 
    bloom_filter_fp_chance = 0.01
    AND caching = {'keys': 'ALL', 'rows_per_partition': 'ALL'}
    AND compaction = {'class': 'LeveledCompactionStrategy'}
    AND compression = {'class': 'LZ4Compressor'}
    AND default_time_to_live = 0
    AND gc_grace_seconds = 864000;
```

#### Table: `url_counters` (Click Count - Counter Table)

```cql
CREATE TABLE url_counters (
    short_code  TEXT PRIMARY KEY,
    click_count COUNTER
);

-- Increment on each click (or batch update)
-- UPDATE url_counters SET click_count = click_count + 1 WHERE short_code = 'abc123';
```

#### Table: `url_dedup` (Deduplication Lookup)

```cql
CREATE TABLE url_dedup (
    long_url_hash   TEXT,
    short_code      TEXT,
    created_at      TIMESTAMP,
    
    PRIMARY KEY (long_url_hash)
) WITH 
    compaction = {'class': 'LeveledCompactionStrategy'};
```

#### Table: `urls_by_user` (User's URLs - Materialized View Alternative)

```cql
CREATE TABLE urls_by_user (
    user_id         UUID,
    created_at      TIMESTAMP,
    short_code      TEXT,
    long_url        TEXT,
    
    PRIMARY KEY ((user_id), created_at, short_code)
) WITH CLUSTERING ORDER BY (created_at DESC);

-- Query: SELECT * FROM urls_by_user WHERE user_id = ? LIMIT 20;
```

**Data Model Visualization:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Cassandra Data Model                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  urls (Partition Key: short_code)                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Partition: abc123                                               │    │
│  │  ├── long_url: "https://example.com/very/long/url"              │    │
│  │  ├── long_url_hash: "a1b2c3d4..."                               │    │
│  │  ├── user_id: 550e8400-e29b-41d4-a716-446655440000              │    │
│  │  ├── is_custom: false                                           │    │
│  │  ├── created_at: 2026-02-03 06:30:00                            │    │
│  │  └── expires_at: 2027-02-03 06:30:00                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  url_dedup (Partition Key: long_url_hash)                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Partition: a1b2c3d4e5f6...                                      │    │
│  │  └── short_code: "abc123"                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  urls_by_user (Partition Key: user_id, Clustering: created_at DESC)     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Partition: 550e8400-e29b-41d4-a716-446655440000                 │    │
│  │  ├── Row: (2026-02-03, abc123) → long_url: "..."                │    │
│  │  ├── Row: (2026-02-02, xyz789) → long_url: "..."                │    │
│  │  └── Row: (2026-02-01, def456) → long_url: "..."                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 4. ClickHouse Analytics Architecture

**Cluster Configuration:**
- 3 shards × 2 replicas = 6 nodes
- ZooKeeper for coordination
- Distributed tables for queries across shards

**Tables:**

```sql
-- Raw click events (ReplacingMergeTree for deduplication)
CREATE TABLE url_clicks ON CLUSTER '{cluster}'
(
    event_id        UUID,
    short_code      LowCardinality(String),
    clicked_at      DateTime64(3),
    
    -- Request metadata
    ip_address      IPv4,
    user_agent      String,
    referer         String,
    
    -- Derived dimensions (populated by Kafka consumer)
    country_code    LowCardinality(FixedString(2)),
    city            LowCardinality(String),
    device_type     Enum8('desktop' = 1, 'mobile' = 2, 'tablet' = 3, 'bot' = 4),
    browser         LowCardinality(String),
    os              LowCardinality(String),
    
    -- Partitioning
    event_date      Date DEFAULT toDate(clicked_at)
)
ENGINE = ReplicatedMergeTree('/clickhouse/tables/{shard}/url_clicks', '{replica}')
PARTITION BY toYYYYMM(event_date)
ORDER BY (short_code, clicked_at, event_id)
TTL event_date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Distributed table for querying across shards
CREATE TABLE url_clicks_distributed ON CLUSTER '{cluster}'
AS url_clicks
ENGINE = Distributed('{cluster}', default, url_clicks, cityHash64(short_code));
```

**Materialized Views for Fast Aggregations:**

```sql
-- Daily aggregates (auto-updated)
CREATE MATERIALIZED VIEW url_analytics_daily ON CLUSTER '{cluster}'
ENGINE = ReplicatedSummingMergeTree('/clickhouse/tables/{shard}/url_analytics_daily', '{replica}')
PARTITION BY toYYYYMM(event_date)
ORDER BY (short_code, event_date)
AS SELECT
    short_code,
    event_date,
    count() AS total_clicks,
    uniqHLL12(ip_address) AS unique_visitors,
    
    -- Device breakdown
    countIf(device_type = 'desktop') AS desktop_clicks,
    countIf(device_type = 'mobile') AS mobile_clicks,
    countIf(device_type = 'tablet') AS tablet_clicks,
    
    -- Top countries (using groupArray)
    topK(10)(country_code) AS top_countries
FROM url_clicks
GROUP BY short_code, event_date;

-- Hourly aggregates for real-time dashboard
CREATE MATERIALIZED VIEW url_analytics_hourly ON CLUSTER '{cluster}'
ENGINE = ReplicatedSummingMergeTree('/clickhouse/tables/{shard}/url_analytics_hourly', '{replica}')
PARTITION BY toYYYYMMDD(event_hour)
ORDER BY (short_code, event_hour)
TTL event_hour + INTERVAL 7 DAY  -- Keep only 7 days of hourly data
AS SELECT
    short_code,
    toStartOfHour(clicked_at) AS event_hour,
    count() AS clicks,
    uniqHLL12(ip_address) AS unique_ips
FROM url_clicks
GROUP BY short_code, event_hour;
```

**Data Flow:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ClickHouse Analytics Pipeline                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐     ┌──────────────┐     ┌────────────────────────┐  │
│   │    Kafka     │────▶│   Kafka      │────▶│   ClickHouse           │  │
│   │   Topic      │     │   Consumer   │     │   url_clicks           │  │
│   │click_events  │     │  (Batch)     │     │                        │  │
│   └──────────────┘     └──────────────┘     └────────────┬───────────┘  │
│                                                          │              │
│                              ┌────────────────────────────┤              │
│                              │                            │              │
│                              ▼                            ▼              │
│                    ┌─────────────────────┐    ┌─────────────────────┐   │
│                    │url_analytics_daily  │    │url_analytics_hourly │   │
│                    │(Materialized View)  │    │(Materialized View)  │   │
│                    └─────────────────────┘    └─────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flows

### Flow 1: URL Creation (Shorten)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              URL CREATION FLOW                                      │
│                              Latency Target: <500ms                                 │
└────────────────────────────────────────────────────────────────────────────────────┘

     Client                API Server              Redis                 Cassandra
        │                      │                     │                       │
        │  POST /shorten       │                     │                       │
        │  {long_url}          │                     │                       │
        │─────────────────────▶│                     │                       │
        │                      │                     │                       │
        │                      │  1. Validate URL    │                       │
        │                      │  2. Hash long_url   │                       │
        │                      │     (SHA-256)       │                       │
        │                      │                     │                       │
        │                      │  3. Check dedup     │                       │
        │                      │─────────────────────▶                       │
        │                      │     GET dedup:{hash}│                       │
        │                      │◀────────────────────│                       │
        │                      │                     │                       │
        │                      │  [CACHE MISS]       │                       │
        │                      │                     │  4. Check dedup table │
        │                      │─────────────────────┼──────────────────────▶│
        │                      │◀────────────────────┼───────────────────────│
        │                      │                     │                       │
        │                      │  [NOT FOUND - New URL]                      │
        │                      │                     │                       │
        │                      │  5. Check blocklist │                       │
        │                      │─────────────────────▶                       │
        │                      │◀────────────────────│                       │
        │                      │                     │                       │
        │                      │  6. Generate ID     │                       │
        │                      │─────────────────────▶                       │
        │                      │     INCR counter    │                       │
        │                      │◀────────────────────│                       │
        │                      │     → Base62 encode │                       │
        │                      │                     │                       │
        │                      │  7. Insert URL      │                       │
        │                      │─────────────────────┼──────────────────────▶│
        │                      │  (Batch: urls +     │   INSERT urls         │
        │                      │   url_dedup +       │   INSERT url_dedup    │
        │                      │   urls_by_user)     │   INSERT urls_by_user │
        │                      │◀────────────────────┼───────────────────────│
        │                      │                     │                       │
        │                      │  8. Cache URL       │                       │
        │                      │─────────────────────▶                       │
        │                      │    SET url:{code}   │                       │
        │                      │    SET dedup:{hash} │                       │
        │                      │◀────────────────────│                       │
        │                      │                     │                       │
        │  201 Created         │                     │                       │
        │  {short_url}         │                     │                       │
        │◀─────────────────────│                     │                       │
        │                      │                     │                       │
```

### Flow 2: URL Redirect (Read Path - Hot Path)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              URL REDIRECT FLOW                                      │
│                              Latency Target: <100ms                                 │
│                              Expected: 40K-200K TPS                                 │
└────────────────────────────────────────────────────────────────────────────────────┘

     Client                API Server              Redis                 Cassandra          Kafka
        │                      │                     │                       │                │
        │  GET /{short_code}   │                     │                       │                │
        │─────────────────────▶│                     │                       │                │
        │                      │                     │                       │                │
        │                      │  1. Check cache     │                       │                │
        │                      │─────────────────────▶                       │                │
        │                      │    GET url:{code}   │                       │                │
        │                      │◀────────────────────│                       │                │
        │                      │                     │                       │                │
        │                      │  [CACHE HIT - 95%+] │                       │                │
        │                      │                     │                       │                │
        │                      │  2. Async: Log click│                       │                │
        │                      │─────────────────────┼───────────────────────┼───────────────▶│
        │                      │    (fire-and-forget)│                       │                │
        │                      │                     │                       │                │
        │  302 Redirect        │                     │                       │                │
        │  Location: {long_url}│                     │                       │                │
        │◀─────────────────────│                     │                       │                │
        │                      │                     │                       │                │
        ├──────────────────────┼─────────────────────┼───────────────────────┼────────────────┤
        │                      │                     │                       │                │
        │                      │  [CACHE MISS - 5%]  │                       │                │
        │                      │                     │                       │                │
        │                      │  3. Query Cassandra │                       │                │
        │                      │─────────────────────┼──────────────────────▶│                │
        │                      │                     │  SELECT * FROM urls   │                │
        │                      │                     │  WHERE short_code=?   │                │
        │                      │◀────────────────────┼───────────────────────│                │
        │                      │                     │                       │                │
        │                      │  [NOT FOUND]        │                       │                │
        │  404 Not Found       │◀────────────────────┤                       │                │
        │◀─────────────────────│                     │                       │                │
        │                      │                     │                       │                │
        │                      │  [EXPIRED]          │                       │                │
        │  410 Gone            │◀────────────────────┤                       │                │
        │◀─────────────────────│                     │                       │                │
        │                      │                     │                       │                │
        │                      │  [FOUND]            │                       │                │
        │                      │  4. Cache result    │                       │                │
        │                      │─────────────────────▶                       │                │
        │                      │    SETEX url:{code} │                       │                │
        │                      │                     │                       │                │
        │                      │  5. Async: Log click│                       │                │
        │                      │─────────────────────┼───────────────────────┼───────────────▶│
        │                      │                     │                       │                │
        │  302 Redirect        │                     │                       │                │
        │◀─────────────────────│                     │                       │                │
```

### Flow 3: Analytics Ingestion

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                           ANALYTICS INGESTION FLOW                                  │
│                           Async, Eventual Consistency                               │
└────────────────────────────────────────────────────────────────────────────────────┘

  API Server               Kafka                  Consumer               ClickHouse
      │                      │                       │                       │
      │  Produce click event │                       │                       │
      │  {short_code,        │                       │                       │
      │   timestamp,         │                       │                       │
      │   ip, user_agent,    │                       │                       │
      │   referer}           │                       │                       │
      │─────────────────────▶│                       │                       │
      │                      │                       │                       │
      │                      │  Batch consume        │                       │
      │                      │  (every 5s or 1000    │                       │
      │                      │   events)             │                       │
      │                      │──────────────────────▶│                       │
      │                      │                       │                       │
      │                      │                       │  1. Parse user_agent  │
      │                      │                       │  2. GeoIP lookup      │
      │                      │                       │  3. Enrich event      │
      │                      │                       │                       │
      │                      │                       │  Batch INSERT         │
      │                      │                       │──────────────────────▶│
      │                      │                       │                       │
      │                      │                       │                       │  Materialized
      │                      │                       │                       │  Views auto-
      │                      │                       │                       │  update
      │                      │                       │                       │
      │                      │  Commit offset        │                       │
      │                      │◀──────────────────────│                       │
      │                      │                       │                       │
```

---

## Short Code Generation Strategy

### Option 1: Counter-Based (Recommended for Simplicity)

```
┌─────────────────────────────────────────────────────────────────┐
│                  Counter-Based ID Generation                    │
└─────────────────────────────────────────────────────────────────┘

Redis: INCR shortcode:counter → 1000000001

Base62 Encoding:
1000000001 → "15FTGg" (6 characters)

Characters: 0-9, a-z, A-Z (62 chars)
6 chars = 62^6 = 56.8 billion unique codes ✓

Implementation:
┌──────────────────────────────────────────────────────────────┐
│  counter = redis.incr("shortcode:counter")                   │
│  short_code = base62_encode(counter)                         │
│                                                              │
│  # Add randomness to prevent enumeration                     │
│  counter = redis.incrby("shortcode:counter", random(1,100))  │
└──────────────────────────────────────────────────────────────┘
```

### Option 2: Pre-allocated Ranges (For High Throughput)

```
┌─────────────────────────────────────────────────────────────────┐
│                  Pre-allocated ID Ranges                        │
└─────────────────────────────────────────────────────────────────┘

Each API server gets a range of 10,000 IDs from Redis:

Server 1: [1-10000]        → generates abc123, abc124, ...
Server 2: [10001-20000]    → generates xyz789, xyz790, ...
Server 3: [20001-30000]    → generates def456, def457, ...

When range exhausted:
redis.incrby("shortcode:range", 10000) → get next range

Benefits:
- No Redis call per URL creation
- Higher throughput
- Each server operates independently
```

---

## Caching Strategy

### Multi-Level Cache

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Multi-Level Caching                               │
└─────────────────────────────────────────────────────────────────────────────┘

  Request
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L1: CDN Edge Cache (CloudFlare)                                            │
│  - TTL: 5 minutes for popular URLs                                          │
│  - Cache-Control: public, max-age=300                                       │
│  - Expected hit rate: 30-40%                                                │
└───────────────────────────────────────────┬─────────────────────────────────┘
                                            │ MISS
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L2: Application Memory (LRU)                                               │
│  - Size: 100K entries per server                                            │
│  - TTL: 5 minutes                                                           │
│  - Expected hit rate: 20%                                                   │
└───────────────────────────────────────────┬─────────────────────────────────┘
                                            │ MISS
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L3: Redis Cluster                                                          │
│  - TTL: 1 hour or until URL expiry                                          │
│  - Expected hit rate: 45%                                                   │
│  - Memory: ~10GB for 10M hot URLs                                           │
└───────────────────────────────────────────┬─────────────────────────────────┘
                                            │ MISS
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L4: Cassandra                                                              │
│  - Source of truth                                                          │
│  - ~5% of requests reach here                                               │
└─────────────────────────────────────────────────────────────────────────────┘

Overall Cache Hit Rate: 95%+
```

---

## Failure Handling & Resilience

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Failure Scenarios                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┬─────────────────────────────────────────────────────┐
│ Component Failure    │ Handling Strategy                                   │
├──────────────────────┼─────────────────────────────────────────────────────┤
│ Redis unavailable    │ - Fallback to Cassandra directly                    │
│                      │ - Circuit breaker opens after 5 failures            │
│                      │ - Degraded mode: higher latency, still functional   │
├──────────────────────┼─────────────────────────────────────────────────────┤
│ Cassandra node down  │ - Automatic failover (RF=3)                         │
│                      │ - LOCAL_QUORUM ensures reads succeed                │
│                      │ - Hinted handoff for writes                         │
├──────────────────────┼─────────────────────────────────────────────────────┤
│ Kafka unavailable    │ - Buffer clicks in memory (bounded queue)           │
│                      │ - Log to local file as backup                       │
│                      │ - Analytics delayed, not lost                       │
├──────────────────────┼─────────────────────────────────────────────────────┤
│ ClickHouse down      │ - Kafka retains events (retention: 7 days)          │
│                      │ - Backfill when recovered                           │
│                      │ - Analytics API returns cached/stale data           │
├──────────────────────┼─────────────────────────────────────────────────────┤
│ Full datacenter down │ - DNS failover to secondary DC                      │
│                      │ - Cassandra multi-DC replication                    │
│                      │ - ~30s failover time                                │
└──────────────────────┴─────────────────────────────────────────────────────┘
```

---

## Infrastructure Sizing

### For 200K TPS Peak (Read), 2K TPS Peak (Write)

| Component | Specification | Count | Purpose |
|-----------|--------------|-------|---------|
| **API Servers** | 8 vCPU, 16GB RAM | 20-50 | Horizontal scaling |
| **Redis Cluster** | 16GB RAM | 6 (3M + 3R) | Cache layer |
| **Cassandra** | 16 vCPU, 64GB RAM, 2TB NVMe | 9-12 | Primary storage |
| **Kafka** | 8 vCPU, 32GB RAM | 6 (3 brokers × 2) | Event streaming |
| **ClickHouse** | 16 vCPU, 128GB RAM, 4TB NVMe | 6 (3S × 2R) | Analytics |
| **Load Balancer** | L7 (Application) | 2 (HA pair) | Traffic distribution |

---

## Monitoring & Observability

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Monitoring Stack                               │
└─────────────────────────────────────────────────────────────────────────────┘

Metrics (Prometheus + Grafana):
├── Request latency (p50, p95, p99)
├── Throughput (requests/sec)
├── Cache hit rates (Redis, CDN)
├── Error rates (4xx, 5xx)
├── Cassandra latency & availability
├── Kafka consumer lag
└── ClickHouse query performance

Logging (ELK Stack):
├── Structured JSON logs
├── Request tracing (correlation IDs)
└── Error aggregation

Alerting:
├── P99 latency > 200ms
├── Error rate > 0.1%
├── Cache hit rate < 90%
├── Kafka lag > 10000
└── Disk usage > 80%
```

---

## Next Steps

1. **Define API Contracts** - OpenAPI/Swagger specification
2. **Create Cassandra Schema** - CQL migration files
3. **Create ClickHouse Schema** - SQL migration files  
4. **Design Kafka Topics** - Topic configuration
5. **Implement Short Code Generation** - Algorithm code
6. **Setup Infrastructure** - Docker Compose for local dev
