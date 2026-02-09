"""
Security utilities for URL shortener.

Provides:
- URL validation and blocklist checking
- Custom alias validation
- Input sanitization
"""

import re
import hashlib
from urllib.parse import urlparse
from typing import Optional
from fastapi import HTTPException


class SecurityValidator:
    """Security validation for URLs and aliases."""
    
    # Reserved short codes that cannot be used as custom aliases
    RESERVED_CODES = frozenset({
        # API endpoints
        'health', 'stats', 'shorten', 'api', 'admin', 'docs', 'redoc', 'openapi',
        # Common paths
        'login', 'logout', 'register', 'signup', 'signin', 'auth', 'oauth',
        'user', 'users', 'account', 'profile', 'settings', 'dashboard',
        'static', 'assets', 'images', 'css', 'js', 'favicon.ico', 'robots.txt',
        # Security sensitive
        'admin', 'root', 'administrator', 'system', 'config', 'env',
        '.env', '.git', '.well-known',
    })
    
    # Blocked domain patterns (known malicious or suspicious TLDs)
    BLOCKED_TLDS = frozenset({
        'tk', 'ml', 'ga', 'cf', 'gq',  # Free TLDs commonly abused
    })
    
    # Known malicious domains (sample list - in production, use external blocklist)
    BLOCKED_DOMAINS = frozenset({
        'malware.com', 'phishing.com', 'evil.com',
        # Add more from threat intelligence feeds
    })
    
    # Blocked URL patterns (regex)
    BLOCKED_PATTERNS = [
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'data:', re.IGNORECASE),
        re.compile(r'vbscript:', re.IGNORECASE),
        re.compile(r'file://', re.IGNORECASE),
    ]
    
    # Valid custom alias pattern: alphanumeric, hyphens, underscores, 3-30 chars
    ALIAS_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{2,29}$')
    
    @classmethod
    def validate_url(cls, url: str) -> tuple[bool, Optional[str]]:
        """
        Validate URL for security issues.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ('http', 'https'):
                return False, f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."
            
            # Check for dangerous patterns
            for pattern in cls.BLOCKED_PATTERNS:
                if pattern.search(url):
                    return False, "URL contains blocked pattern"
            
            # Extract domain
            domain = parsed.netloc.lower()
            if ':' in domain:
                domain = domain.split(':')[0]  # Remove port
            
            # Check TLD
            tld = domain.split('.')[-1] if '.' in domain else ''
            if tld in cls.BLOCKED_TLDS:
                return False, f"URLs from .{tld} domains are not allowed"
            
            # Check blocked domains
            if domain in cls.BLOCKED_DOMAINS:
                return False, "This domain is blocked"
            
            # Check for IP-based URLs (often suspicious)
            ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
            if ip_pattern.match(domain):
                return False, "IP-based URLs are not allowed"
            
            # Check URL length
            if len(url) > 2048:
                return False, "URL too long (max 2048 characters)"
            
            return True, None
            
        except Exception as e:
            return False, f"Invalid URL format: {str(e)}"
    
    @classmethod
    def validate_custom_alias(cls, alias: str) -> tuple[bool, Optional[str]]:
        """
        Validate custom alias for security and format.
        
        Returns:
            (is_valid, error_message)
        """
        if not alias:
            return True, None  # Empty is OK (will auto-generate)
        
        # Check length
        if len(alias) < 3:
            return False, "Custom alias must be at least 3 characters"
        
        if len(alias) > 30:
            return False, "Custom alias must be at most 30 characters"
        
        # Check pattern
        if not cls.ALIAS_PATTERN.match(alias):
            return False, "Custom alias can only contain letters, numbers, hyphens, and underscores"
        
        # Check reserved words
        alias_lower = alias.lower()
        if alias_lower in cls.RESERVED_CODES:
            return False, f"'{alias}' is a reserved word and cannot be used"
        
        # Check for path traversal attempts
        if '..' in alias or '/' in alias or '\\' in alias:
            return False, "Invalid characters in alias"
        
        # Check for URL encoding attacks
        if '%' in alias:
            return False, "Encoded characters not allowed in alias"
        
        return True, None
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Sanitize URL by removing potentially dangerous characters."""
        # Remove null bytes
        url = url.replace('\x00', '')
        # Remove control characters
        url = ''.join(c for c in url if ord(c) >= 32 or c in '\t\n\r')
        return url.strip()
    
    @classmethod
    def check_url_safety(cls, url: str) -> None:
        """
        Check URL safety and raise HTTPException if unsafe.
        
        Raises:
            HTTPException: If URL is not safe
        """
        sanitized = cls.sanitize_url(url)
        is_valid, error = cls.validate_url(sanitized)
        
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"URL validation failed: {error}"
            )
    
    @classmethod
    def check_alias_safety(cls, alias: Optional[str]) -> None:
        """
        Check custom alias safety and raise HTTPException if unsafe.
        
        Raises:
            HTTPException: If alias is not safe
        """
        if alias:
            is_valid, error = cls.validate_custom_alias(alias)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Custom alias validation failed: {error}"
                )


# Domain blocklist manager (can be extended to load from external sources)
class BlocklistManager:
    """Manage URL blocklist from external sources."""
    
    def __init__(self):
        self._domains: set[str] = set()
        self._last_updated = None
    
    def add_domain(self, domain: str):
        """Add a domain to the blocklist."""
        self._domains.add(domain.lower())
    
    def remove_domain(self, domain: str):
        """Remove a domain from the blocklist."""
        self._domains.discard(domain.lower())
    
    def is_blocked(self, domain: str) -> bool:
        """Check if a domain is blocked."""
        domain = domain.lower()
        # Check exact match
        if domain in self._domains:
            return True
        # Check parent domains
        parts = domain.split('.')
        for i in range(len(parts) - 1):
            parent = '.'.join(parts[i:])
            if parent in self._domains:
                return True
        return False
    
    def load_from_file(self, filepath: str):
        """Load blocklist from a file (one domain per line)."""
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    domain = line.strip()
                    if domain and not domain.startswith('#'):
                        self.add_domain(domain)
        except FileNotFoundError:
            pass  # Blocklist file is optional


# Singleton instance
blocklist = BlocklistManager()
validator = SecurityValidator()
