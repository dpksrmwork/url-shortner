"""
Security headers middleware for URL shortener.

Adds security headers to all responses to prevent common web attacks.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.
    
    Headers added:
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Legacy XSS protection
    - Content-Security-Policy: Controls resource loading
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    - Strict-Transport-Security: Forces HTTPS (when enabled)
    """
    
    def __init__(self, app, enable_hsts: bool = False):
        """
        Initialize security headers middleware.
        
        Args:
            app: FastAPI application
            enable_hsts: Enable HSTS header (only enable in production with HTTPS)
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Legacy XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Content Security Policy
        # Note: Relaxed for API, stricter for web pages
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Control browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )
        
        # Prevent caching of sensitive data
        if request.url.path.startswith('/stats'):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        
        # HSTS (only enable when running behind HTTPS)
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        return response


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """
    Secure CORS middleware with strict origin validation.
    
    More restrictive than default CORS middleware.
    """
    
    def __init__(self, app, allowed_origins: list[str] = None):
        """
        Initialize CORS middleware.
        
        Args:
            app: FastAPI application
            allowed_origins: List of allowed origins (e.g., ["https://example.com"])
        """
        super().__init__(app)
        self.allowed_origins = set(allowed_origins or [])
    
    async def dispatch(self, request: Request, call_next: Callable):
        origin = request.headers.get("Origin")
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            if origin and (origin in self.allowed_origins or "*" in self.allowed_origins):
                return self._preflight_response(origin)
            else:
                # Reject unauthorized preflight
                from fastapi.responses import Response
                return Response(status_code=403)
        
        response = await call_next(request)
        
        # Add CORS headers for allowed origins
        if origin and (origin in self.allowed_origins or "*" in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = (
                "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"
            )
        
        return response
    
    def _preflight_response(self, origin: str):
        from fastapi.responses import Response
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "86400",  # Cache preflight for 24 hours
            }
        )
