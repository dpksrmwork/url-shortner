"""
Redis caching layer for URL shortener.

Implements the caching strategy from HLD:
- URL Cache: short_code → long_url (cache-aside for redirects)
- Dedup Cache: url_hash → short_code (write-through for creation)
"""

import redis
import json
from typing import Optional
from app.core.config import settings


class RedisCache:
    """Redis cache manager with connection pooling."""
    
    # Cache key prefixes
    URL_PREFIX = "url:"
    DEDUP_PREFIX = "dedup:"
    
    # TTL in seconds
    URL_TTL = 3600  # 1 hour
    DEDUP_TTL = 86400  # 24 hours
    
    def __init__(self):
        self.pool = None
        self.client = None
    
    def connect(self):
        """Initialize Redis connection pool."""
        self.pool = redis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        self.client = redis.Redis(connection_pool=self.pool)
        
        # Test connection
        try:
            self.client.ping()
        except redis.ConnectionError as e:
            print(f"Warning: Redis connection failed: {e}. Caching disabled.")
            self.client = None
    
    def disconnect(self):
        """Close Redis connections."""
        if self.pool:
            self.pool.disconnect()
    
    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except redis.ConnectionError:
            return False
    
    # ============ URL Cache (short_code → long_url) ============
    
    def get_url(self, short_code: str) -> Optional[str]:
        """
        Get long URL from cache.
        Returns None on cache miss or if Redis unavailable.
        """
        if not self.client:
            return None
        try:
            key = f"{self.URL_PREFIX}{short_code}"
            return self.client.get(key)
        except redis.RedisError:
            return None
    
    def set_url(self, short_code: str, long_url: str, ttl: int = None) -> bool:
        """
        Cache a URL mapping.
        Uses URL_TTL (1 hour) by default, or custom TTL if provided.
        """
        if not self.client:
            return False
        try:
            key = f"{self.URL_PREFIX}{short_code}"
            self.client.setex(key, ttl or self.URL_TTL, long_url)
            return True
        except redis.RedisError:
            return False
    
    def delete_url(self, short_code: str) -> bool:
        """Remove URL from cache (for expiration/deletion)."""
        if not self.client:
            return False
        try:
            key = f"{self.URL_PREFIX}{short_code}"
            self.client.delete(key)
            return True
        except redis.RedisError:
            return False
    
    # ============ Dedup Cache (url_hash → short_code) ============
    
    def get_dedup(self, url_hash: str) -> Optional[str]:
        """
        Get existing short_code for a URL hash.
        Returns None on cache miss.
        """
        if not self.client:
            return None
        try:
            key = f"{self.DEDUP_PREFIX}{url_hash}"
            return self.client.get(key)
        except redis.RedisError:
            return None
    
    def set_dedup(self, url_hash: str, short_code: str) -> bool:
        """
        Cache dedup mapping (write-through on URL creation).
        Uses DEDUP_TTL (24 hours).
        """
        if not self.client:
            return False
        try:
            key = f"{self.DEDUP_PREFIX}{url_hash}"
            self.client.setex(key, self.DEDUP_TTL, short_code)
            return True
        except redis.RedisError:
            return False
    
    # ============ Bulk Operations ============
    
    def get_urls_bulk(self, short_codes: list[str]) -> dict[str, Optional[str]]:
        """Get multiple URLs in a single pipeline call."""
        if not self.client or not short_codes:
            return {code: None for code in short_codes}
        
        try:
            pipe = self.client.pipeline(transaction=False)
            for code in short_codes:
                pipe.get(f"{self.URL_PREFIX}{code}")
            results = pipe.execute()
            return dict(zip(short_codes, results))
        except redis.RedisError:
            return {code: None for code in short_codes}
    
    # ============ Stats ============
    
    def get_cache_stats(self) -> dict:
        """Get Redis cache statistics."""
        if not self.client:
            return {"status": "unavailable"}
        
        try:
            info = self.client.info("stats")
            memory = self.client.info("memory")
            return {
                "status": "connected",
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "used_memory_human": memory.get("used_memory_human", "unknown"),
            }
        except redis.RedisError as e:
            return {"status": "error", "error": str(e)}


# Singleton instance
cache = RedisCache()
