"""
URL shortening service with Redis caching and security validation.

Implements:
- Cache-aside pattern for reads (redirects)
- Write-through pattern for deduplication
- URL and alias security validation
"""

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import hashlib
import base64
import secrets
from app.db.cassandra import db
from app.db.redis import cache
from app.models.schemas import ShortenRequest, ShortenResponse, URLStats
from app.core.config import settings
from app.core.security import SecurityValidator
import logging

logger = logging.getLogger(__name__)


class URLService:
    """Service for URL shortening operations."""
    
    @staticmethod
    def generate_short_code(url: str) -> str:
        """
        Generate a short code from URL.
        
        Uses SHA-256 hash + random bytes to prevent enumeration attacks.
        """
        # Combine URL hash with random bytes for unpredictability
        hash_bytes = hashlib.sha256(url.encode()).digest()[:4]
        random_bytes = secrets.token_bytes(2)
        combined = hash_bytes + random_bytes
        return base64.urlsafe_b64encode(combined).decode()[:8]
    
    @staticmethod
    def get_url_hash(url: str) -> str:
        """Generate SHA-256 hash of URL for deduplication."""
        return hashlib.sha256(url.encode()).hexdigest()
    
    def create_short_url(self, req: ShortenRequest) -> ShortenResponse:
        """
        Create a shortened URL with deduplication and security validation.
        
        Flow:
        1. Validate URL and alias for security
        2. Check Redis dedup cache
        3. Check Cassandra dedup table (on cache miss)
        4. Generate short code if new URL
        5. Write to Cassandra + Redis (write-through)
        """
        url_str = str(req.url)
        
        # Security Step: Validate URL
        SecurityValidator.check_url_safety(url_str)
        
        # Security Step: Validate custom alias
        if req.custom_alias:
            SecurityValidator.check_alias_safety(req.custom_alias)
        
        url_hash = self.get_url_hash(url_str)
        
        # Step 1: Check Redis dedup cache first
        cached_code = cache.get_dedup(url_hash)
        if cached_code:
            return ShortenResponse(
                short_code=cached_code,
                short_url=f"{settings.base_url}/{cached_code}",
                long_url=url_str
            )
        
        # Step 2: Check Cassandra dedup table (cache miss)
        result = db.session.execute(db.prepared_statements['get_dedup'], [url_hash])
        row = result.one()
        if row:
            # Cache the result for future requests
            cache.set_dedup(url_hash, row.short_code)
            return ShortenResponse(
                short_code=row.short_code,
                short_url=f"{settings.base_url}/{row.short_code}",
                long_url=url_str
            )
        
        # Step 3: Generate or use custom alias
        short_code = req.custom_alias if req.custom_alias else self.generate_short_code(url_str)
        
        # Check if short_code already exists
        result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        if result.one():
            if req.custom_alias:
                raise HTTPException(status_code=409, detail="This custom alias is already taken")
            # If auto-generated code collides, regenerate with more randomness
            short_code = base64.urlsafe_b64encode(secrets.token_bytes(6)).decode()[:8]
            result = db.session.execute(db.prepared_statements['get_url'], [short_code])
            if result.one():
                raise HTTPException(status_code=500, detail="Failed to generate unique short code")
        
        # Step 4: Insert URL into Cassandra
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=req.ttl_days)
        
        # Sanitize user_id
        user_id = req.user_id[:100] if req.user_id else None
        
        db.session.execute(db.prepared_statements['insert_url'], 
                          [short_code, url_str, created_at, expires_at, user_id])
        db.session.execute(db.prepared_statements['insert_dedup'], 
                          [url_hash, short_code, created_at])
        
        # Write-through: Cache the new URL and dedup mapping
        cache.set_url(short_code, url_str)
        cache.set_dedup(url_hash, short_code)
        
        return ShortenResponse(
            short_code=short_code,
            short_url=f"{settings.base_url}/{short_code}",
            long_url=url_str
        )
    
    def get_long_url(self, short_code: str) -> str:
        """
        Get the original URL for redirection.
        
        Flow (cache-aside pattern):
        1. Validate short_code format
        2. Check Redis cache for URL
        3. On cache miss, query Cassandra
        4. Cache the result
        5. Increment click counter asynchronously
        """
        # Security: Validate short_code format
        if not short_code or len(short_code) > 30:
            raise HTTPException(status_code=404, detail="URL not found")
        
        # Only allow alphanumeric, hyphens, underscores
        if not all(c.isalnum() or c in '-_' for c in short_code):
            raise HTTPException(status_code=404, detail="URL not found")
        
        # Step 1: Check Redis cache first
        cached_url = cache.get_url(short_code)
        if cached_url:
            # Increment click count asynchronously (fire-and-forget)
            future = db.session.execute_async(db.prepared_statements['increment_clicks'], [short_code])
            future.add_errback(lambda exc: logger.error(f"Click async increment failed: {exc}"))
            return cached_url
        
        # Step 2: Cache miss - query Cassandra
        result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        row = result.one()
        
        if not row:
            raise HTTPException(status_code=404, detail="URL not found")
        
        if row.expires_at:
            # Make expires_at timezone-aware if it's naive
            expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                # Remove expired URL from cache if it exists
                cache.delete_url(short_code)
                raise HTTPException(status_code=410, detail="URL expired")
        
        # Step 3: Cache the result for future requests
        cache.set_url(short_code, row.long_url)
        
        # Step 4: Increment click count asynchronously
        future = db.session.execute_async(db.prepared_statements['increment_clicks'], [short_code])
        future.add_errback(lambda exc: logger.error(f"Click async increment failed: {exc}"))
        
        return row.long_url
    
    def get_stats(self, short_code: str) -> URLStats:
        """Get statistics for a shortened URL."""
        # Security: Validate short_code format
        if not short_code or len(short_code) > 30:
            raise HTTPException(status_code=404, detail="URL not found")
        
        if not all(c.isalnum() or c in '-_' for c in short_code):
            raise HTTPException(status_code=404, detail="URL not found")
        
        url_result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        url_row = url_result.one()
        
        if not url_row:
            raise HTTPException(status_code=404, detail="URL not found")
        
        clicks_result = db.session.execute(db.prepared_statements['get_clicks'], [short_code])
        clicks_row = clicks_result.one()
        
        return URLStats(
            short_code=short_code,
            long_url=url_row.long_url,
            clicks=clicks_row.click_count if clicks_row else 0,
            expires_at=url_row.expires_at
        )


url_service = URLService()
