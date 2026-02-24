"""
Pydantic schemas for URL shortener with security validation.
"""

from pydantic import BaseModel, HttpUrl, field_validator, Field
from datetime import datetime
from typing import Optional
import re


class ShortenRequest(BaseModel):
    """Request model for creating a shortened URL."""
    
    url: HttpUrl = Field(..., description="The URL to shorten")
    custom_alias: Optional[str] = Field(
        None, 
        min_length=3, 
        max_length=30,
        description="Custom alias for the short URL"
    )
    user_id: Optional[str] = Field(
        None, 
        max_length=100,
        description="User identifier for tracking"
    )
    ttl_days: int = Field(
        default=1095,  # 3 years
        ge=1,
        le=3650,  # Max 10 years
        description="Time to live in days"
    )
    
    @field_validator('custom_alias')
    @classmethod
    def validate_custom_alias(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom alias format and safety."""
        if v is None:
            return v
        
        # Check pattern: alphanumeric, hyphens, underscores
        pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
        if not pattern.match(v):
            raise ValueError(
                'Custom alias must start with a letter or number and contain only '
                'letters, numbers, hyphens, and underscores'
            )
        
        # Check for reserved words
        reserved = {
            'health', 'stats', 'shorten', 'api', 'admin', 'docs', 'redoc',
            'login', 'logout', 'register', 'auth', 'oauth', 'user', 'users',
            'static', 'assets', 'favicon', 'robots', '.env', '.git'
        }
        if v.lower() in reserved:
            raise ValueError(f"'{v}' is a reserved word and cannot be used")
        
        # Check for path traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid characters in alias')
        
        return v
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize user ID."""
        if v is None:
            return v
        # Only allow alphanumeric characters, hyphens, underscores, and dots
        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '', v)
        return sanitized[:100]  # Enforce max length
    
    @field_validator('url')
    @classmethod
    def validate_url_safety(cls, v: HttpUrl) -> HttpUrl:
        """Additional URL validation beyond Pydantic's HttpUrl."""
        url_str = str(v)
        
        # Check URL length
        if len(url_str) > 2048:
            raise ValueError('URL too long (max 2048 characters)')
        
        # Block dangerous schemes (should be caught by HttpUrl, but double-check)
        if url_str.lower().startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
            raise ValueError('Invalid URL scheme')
        
        return v


class ShortenResponse(BaseModel):
    """Response model for shortened URL."""
    
    short_code: str = Field(..., description="The short code")
    short_url: str = Field(..., description="The complete short URL")
    long_url: str = Field(..., description="The original URL")


class URLStats(BaseModel):
    """Statistics for a shortened URL."""
    
    short_code: str = Field(..., description="The short code")
    long_url: str = Field(..., description="The original URL")
    clicks: int = Field(..., ge=0, description="Number of clicks")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    detail: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
