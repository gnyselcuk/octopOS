"""Rate limiting middleware for webhook endpoints.

This module provides rate limiting functionality to prevent DoS attacks
on webhook endpoints.
"""

import time
import threading
from collections import defaultdict
from typing import Dict, Optional


class RateLimiter:
    """Token bucket rate limiter for API endpoints.
    
    This implementation is thread-safe and uses a token bucket algorithm
    to allow bursting while maintaining average rate limits.
    """
    
    def __init__(self, requests_per_minute: int = 60, burst: int = 10):
        """Initialize the rate limiter.
        
        Args:
            requests_per_minute: Maximum requests allowed per minute
            burst: Maximum burst size (tokens available at once)
        """
        self.rate = requests_per_minute / 60.0  # Convert to per-second rate
        self.burst = burst
        self._buckets: Dict[str, tuple] = {}  # key -> (tokens, last_update)
        self._lock = threading.Lock()
    
    def _refill(self, key: str) -> float:
        """Refill tokens for a given key based on elapsed time."""
        now = time.time()
        if key not in self._buckets:
            self._buckets[key] = (self.burst, now)
            return self.burst
        
        tokens, last_update = self._buckets[key]
        elapsed = now - last_update
        tokens = min(self.burst, tokens + elapsed * self.rate)
        self._buckets[key] = (tokens, now)
        return tokens
    
    def allow(self, key: str, cost: int = 1) -> bool:
        """Check if request is allowed under rate limit.
        
        Args:
            key: Identifier for rate limit (e.g., IP address, user ID)
            cost: Token cost for this request (default: 1)
            
        Returns:
            True if request is allowed, False if rate limited
        """
        with self._lock:
            tokens = self._refill(key)
            
            if tokens >= cost:
                tokens -= cost
                self._buckets[key] = (tokens, time.time())
                return True
            return False
    
    def get_remaining(self, key: str) -> int:
        """Get remaining requests for a key.
        
        Args:
            key: Identifier for rate limit
            
        Returns:
            Number of remaining requests
        """
        with self._lock:
            tokens = self._refill(key)
            return int(tokens)
    
    def reset(self, key: str) -> None:
        """Reset rate limit for a key.
        
        Args:
            key: Identifier to reset
        """
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance.
    
    Returns:
        Singleton RateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        with _rate_limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter(requests_per_minute=60, burst=10)
    return _rate_limiter


def check_rate_limit(key: str, requests_per_minute: int = 60) -> bool:
    """Check if request is within rate limit.
    
    This is a convenience function that uses the global rate limiter.
    
    Args:
        key: Identifier for rate limit (IP, user ID, etc.)
        requests_per_minute: Maximum requests allowed per minute
        
    Returns:
        True if allowed, False if rate limited
    """
    limiter = get_rate_limiter()
    return limiter.allow(key)


def get_remaining_requests(key: str) -> int:
    """Get remaining requests for a key.
    
    Args:
        key: Identifier for rate limit
        
    Returns:
        Number of remaining requests allowed
    """
    limiter = get_rate_limiter()
    return limiter.get_remaining(key)


class IPRateLimiter:
    """Rate limiter specifically for IP-based limiting.
    
    Provides convenience methods for IP-based rate limiting
    commonly used for webhook endpoints.
    """
    
    def __init__(self, requests_per_minute: int = 30):
        """Initialize IP rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute per IP
        """
        self.requests_per_minute = requests_per_minute
        self._limiter = RateLimiter(
            requests_per_minute=requests_per_minute,
            burst=requests_per_minute // 3  # Allow small bursts
        )
    
    def is_allowed(self, ip_address: str) -> bool:
        """Check if IP is allowed to make a request.
        
        Args:
            ip_address: Client IP address
            
        Returns:
            True if allowed, False if rate limited
        """
        return self._limiter.allow(f"ip:{ip_address}")
    
    def get_remaining(self, ip_address: str) -> int:
        """Get remaining requests for IP.
        
        Args:
            ip_address: Client IP address
            
        Returns:
            Remaining requests
        """
        return self._limiter.get_remaining(f"ip:{ip_address}")
    
    def reset(self, ip_address: str) -> None:
        """Reset rate limit for IP.
        
        Args:
            ip_address: Client IP address
        """
        self._limiter.reset(f"ip:{ip_address}")


# Global IP rate limiter
_ip_limiter: Optional[IPRateLimiter] = None


def get_ip_limiter() -> IPRateLimiter:
    """Get global IP rate limiter.
    
    Returns:
        Singleton IPRateLimiter instance
    """
    global _ip_limiter
    if _ip_limiter is None:
        _ip_limiter = IPRateLimiter(requests_per_minute=30)
    return _ip_limiter
