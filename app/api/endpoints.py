"""
API endpoints for URL shortener with security features.
"""

from fastapi import APIRouter, Request, Path, Query
from fastapi.responses import RedirectResponse, JSONResponse
from app.models.schemas import ShortenRequest, ShortenResponse, URLStats, HealthResponse
from app.services.url_service import url_service
from typing import Annotated
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the service is running"
)
def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@router.post(
    "/shorten", 
    response_model=ShortenResponse,
    responses={
        400: {"description": "Invalid URL or alias"},
        409: {"description": "Custom alias already exists"},
        429: {"description": "Rate limit exceeded"},
    },
    summary="Create a shortened URL",
    description="Shorten a URL with optional custom alias and TTL"
)
def shorten_url(req: ShortenRequest, request: Request):
    """
    Create a shortened URL.
    
    - **url**: The URL to shorten (required)
    - **custom_alias**: Custom short code (optional, 3-30 chars)
    - **user_id**: User identifier for tracking (optional)
    - **ttl_days**: Time to live in days (default: 1095 = 3 years)
    """
    # Log the request (without sensitive data)
    logger.info(f"Shorten request from {request.client.host if request.client else 'unknown'}")
    
    return url_service.create_short_url(req)


@router.get(
    "/stats/{short_code}",
    response_model=URLStats,
    responses={
        404: {"description": "URL not found"},
    },
    summary="Get URL statistics",
    description="Get click count and expiration for a shortened URL"
)
def get_stats(
    short_code: Annotated[str, Path(
        min_length=1,
        max_length=30,
        pattern=r'^[a-zA-Z0-9_-]+$',
        description="The short code to look up"
    )]
):
    """
    Get statistics for a shortened URL.
    
    Returns click count, original URL, and expiration time.
    """
    return url_service.get_stats(short_code)


@router.get(
    "/{short_code}",
    responses={
        301: {"description": "Redirect to original URL"},
        404: {"description": "URL not found"},
        410: {"description": "URL expired"},
    },
    summary="Redirect to original URL",
    description="Resolve short code and redirect to the original URL"
)
def redirect_url(
    short_code: Annotated[str, Path(
        min_length=1,
        max_length=30,
        pattern=r'^[a-zA-Z0-9_-]+$',
        description="The short code to redirect"
    )]
):
    """
    Redirect to the original URL.
    
    Returns a 301 permanent redirect to the original URL.
    Increments click counter asynchronously.
    """
    long_url = url_service.get_long_url(short_code)
    
    # Use 301 for SEO (permanent redirect)
    # Use 302 if you want to track each redirect more accurately
    response = RedirectResponse(url=long_url, status_code=301)
    
    # Add security headers for redirect
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    
    return response
