"""
URL Shortener FastAPI Application.

Security features:
- Rate limiting middleware
- Security headers
- Input validation
- Secure default configuration
"""

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from app.api.endpoints import router
from app.db.cassandra import db
from app.db.redis import cache
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - connect/disconnect databases."""
    logger.info("Starting URL Shortener service...")
    
    # Connect to databases
    try:
        db.connect()
        logger.info("Connected to Cassandra")
    except Exception as e:
        logger.error(f"Failed to connect to Cassandra: {e}")
        raise
    
    try:
        cache.connect()
        if cache.is_available:
            logger.info("Connected to Redis")
        else:
            logger.warning("Redis unavailable - running without cache")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - running without cache")
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down URL Shortener service...")
    cache.disconnect()
    db.disconnect()


app = FastAPI(
    title="URL Shortener",
    description="High-performance URL shortening service with security features",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",  # Can be disabled in production with docs_url=None
    redoc_url="/redoc",
)

# Security Middleware (order matters - first added = last executed)

# 1. Security Headers - adds security headers to all responses
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=False  # Enable when running behind HTTPS
)

# 2. Rate Limiting - prevents abuse
app.add_middleware(
    RateLimitMiddleware,
    redis_client=cache.client if cache.is_available else None
)

# 3. Trusted Host - prevents host header attacks (uncomment in production)
# app.add_middleware(
#     TrustedHostMiddleware,
#     allowed_hosts=["yourdomain.com", "*.yourdomain.com"]
# )


@app.get("/health")
def health_check():
    """
    Health check endpoint for Kubernetes probes.
    
    Returns service status and dependency health.
    """
    return {
        "status": "healthy",
        "cassandra": "connected" if db.session else "disconnected",
        "redis": "connected" if cache.is_available else "unavailable"
    }


@app.get("/")
def root():
    """Root endpoint with service information."""
    return {
        "service": "URL Shortener",
        "version": "1.1.0",
        "docs": "/docs",
        "health": "/health"
    }


# Include routes AFTER static routes to avoid catch-all /{short_code} matching them
app.include_router(router)
