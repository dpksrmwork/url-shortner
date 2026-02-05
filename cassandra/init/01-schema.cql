-- Create keyspace with replication factor 1 for local dev (use 3 in production)
CREATE KEYSPACE IF NOT EXISTS url_shortener
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
}
AND durable_writes = true;

USE url_shortener;

-- Main URLs table: short_code -> URL data
CREATE TABLE IF NOT EXISTS urls (
  short_code text PRIMARY KEY,
  long_url text,
  created_at timestamp,
  expires_at timestamp,
  user_id text
) WITH compaction = {'class': 'LeveledCompactionStrategy'}
  AND gc_grace_seconds = 864000
  AND default_time_to_live = 94608000;

-- URL click counters (separate table for counter columns)
CREATE TABLE IF NOT EXISTS url_clicks (
  short_code text PRIMARY KEY,
  click_count counter
);

-- Deduplication table: URL hash -> short_code
CREATE TABLE IF NOT EXISTS url_dedup (
  url_hash text PRIMARY KEY,
  short_code text,
  created_at timestamp
) WITH compaction = {'class': 'LeveledCompactionStrategy'};

-- Users table
CREATE TABLE IF NOT EXISTS users (
  user_id text PRIMARY KEY,
  email text,
  created_at timestamp
);

-- User URL counters (separate table for counter columns)
CREATE TABLE IF NOT EXISTS user_stats (
  user_id text PRIMARY KEY,
  url_count counter
);

-- Index for looking up URLs by user
CREATE INDEX IF NOT EXISTS urls_by_user ON urls (user_id);
