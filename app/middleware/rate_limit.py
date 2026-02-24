"""
Rate limiting middleware for URL shortener.

Implements sliding window rate limiting using Redis or in-memory fallback.
"""

import time
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int  # Number of requests allowed
    window: int    # Time window in seconds
    

class InMemoryRateLimiter:
    """
    In-memory rate limiter using sliding window.
    Used as fallback when Redis is unavailable.
    """
    
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_task = None
    
    async def _cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(300)  # Clean up every 5 minutes
                await self.cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"RateLimiter cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """
        Check if request is allowed.
        
        Returns:
            (allowed, remaining, reset_time)
        """
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
        async with self._lock:
            now = time.time()
            window_start = now - window
            
            # Remove old requests outside the window
            self._requests[key] = [
                ts for ts in self._requests[key] 
                if ts > window_start
            ]
            
            current_count = len(self._requests[key])
            
            if current_count >= limit:
                # Calculate when the oldest request expires
                oldest = min(self._requests[key]) if self._requests[key] else now
                reset_time = int(oldest + window - now)
                return False, 0, max(1, reset_time)
            
            # Add current request
            self._requests[key].append(now)
            remaining = limit - len(self._requests[key])
            
            return True, remaining, window
    
    async def cleanup(self):
        """Remove expired entries."""
        async with self._lock:
            now = time.time()
            keys_to_remove = []
            for key, timestamps in self._requests.items():
                self._requests[key] = [ts for ts in timestamps if ts > now - 3600]
                if not self._requests[key]:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del self._requests[key]


class RedisRateLimiter:
    """
    Redis-based rate limiter using sliding window.
    More scalable for distributed systems.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """
        Check if request is allowed using Redis sorted sets.
        
        Returns:
            (allowed, remaining, reset_time)
        """
        if not self.redis:
            return True, limit, window  # Allow if Redis unavailable
        
        try:
            now = time.time()
            window_start = now - window
            pipe_key = f"ratelimit:{key}"
            
            def redis_ops():
                pipe = self.redis.pipeline()
                pipe.zremrangebyscore(pipe_key, 0, window_start)
                pipe.zadd(pipe_key, {str(now): now})
                pipe.zcard(pipe_key)
                pipe.expire(pipe_key, window)
                return pipe.execute()
                
            results = await asyncio.to_thread(redis_ops)
            
            current_count = results[2]
            
            if current_count > limit:
                # Remove the request we just added
                await asyncio.to_thread(self.redis.zrem, pipe_key, str(now))
                return False, 0, window
            
            remaining = limit - current_count
            return True, remaining, window
            
        except Exception as e:
            logger.warning(f"Redis rate limit error: {e}")
            return True, limit, window  # Allow on error


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    
    Applies different limits based on endpoint:
    - POST /shorten: Strict limit (prevent abuse)
    - GET /{code}: Higher limit (allow traffic)
    - Other endpoints: Default limit
    """
    
    # Rate limit configurations by endpoint pattern
    LIMITS = {
        'create': RateLimitConfig(requests=100, window=60),      # 100/min for creates
        'redirect': RateLimitConfig(requests=1000, window=60),   # 1000/min for redirects
        'stats': RateLimitConfig(requests=200, window=60),       # 200/min for stats
        'default': RateLimitConfig(requests=500, window=60),     # 500/min default
    }
    
    def __init__(self, app, redis_client=None):
        super().__init__(app)
        if redis_client:
            self.limiter = RedisRateLimiter(redis_client)
        else:
            self.limiter = InMemoryRateLimiter()
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check X-Forwarded-For header (for proxied requests)
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        # Fall back to direct client
        return request.client.host if request.client else "unknown"
    
    def _get_limit_config(self, request: Request) -> tuple[str, RateLimitConfig]:
        """Determine rate limit based on request path and method."""
        path = request.url.path
        method = request.method
        
        if path == '/shorten' and method == 'POST':
            return 'create', self.LIMITS['create']
        elif path.startswith('/stats/'):
            return 'stats', self.LIMITS['stats']
        elif method == 'GET' and not path.startswith('/docs') and not path.startswith('/openapi'):
            return 'redirect', self.LIMITS['redirect']
        else:
            return 'default', self.LIMITS['default']
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request with rate limiting."""
        # Skip rate limiting for health checks
        if request.url.path in ('/health', '/docs', '/openapi.json', '/redoc'):
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        limit_type, config = self._get_limit_config(request)
        
        # Create rate limit key
        key = f"{client_ip}:{limit_type}"
        
        # Check rate limit
        allowed, remaining, reset = await self.limiter.is_allowed(
            key, config.requests, config.window
        )
        
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after": reset
                },
                headers={
                    "X-RateLimit-Limit": str(config.requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                    "Retry-After": str(reset)
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(config.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        
        return response


# Simple function-based rate limiter for specific endpoints
async def rate_limit_check(
    request: Request,
    limit: int = 100,
    window: int = 60
) -> None:
    """
    Dependency injection rate limiter for specific endpoints.
    
    Usage:
        @app.post("/shorten")
        async def create(request: Request, _=Depends(rate_limit_check)):
            ...
    """
    # This would need a global limiter instance
    # For now, it's a placeholder
    pass
