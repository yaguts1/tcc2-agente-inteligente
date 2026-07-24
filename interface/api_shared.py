"""Shared utilities for API routers."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import HTTPException, Request, status
from configuracao import carregar_configuracao

config = carregar_configuracao()
DB_PATH = config.db_path

DEFAULT_PERFIL = "medio"
APP_VERSION = "1.0.0"
APP_START_TIME = time.time()

# Enhanced rate limiting system
class RateLimiter:
    """Flexible rate limiter with configurable windows and limits."""
    
    def __init__(self):
        self._attempts: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()
    
    async def check_limit(self, key: str, limit: int, window_seconds: int, request: Request) -> None:
        """
        Check if request exceeds rate limit.
        
        Args:
            key: Rate limit category (e.g., 'auth', 'api', 'batch')
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            request: FastAPI request object
        """
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        async with self._lock:
            # Clean old attempts
            if client_ip in self._attempts[key]:
                self._attempts[key][client_ip] = [
                    ts for ts in self._attempts[key][client_ip] 
                    if now - ts < window_seconds
                ]
            
            # Count attempts in window
            attempts = len(self._attempts[key].get(client_ip, []))
            
            if attempts >= limit:
                retry_after = window_seconds
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "rate_limited",
                        "message": f"Muitas requisições. Tente novamente em {window_seconds}s.",
                        "retry_after": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Record new attempt
            self._attempts[key][client_ip].append(now)
    
    def reset(self, key: str | None = None) -> None:
        """Reset rate limits (for testing)."""
        if key is None:
            self._attempts.clear()
        elif key in self._attempts:
            self._attempts[key].clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


def _reset_auth_rate_limits() -> None:
    """Reset auth rate limits (for testing only)."""
    rate_limiter.reset('auth')


async def _check_auth_rate_limit(request: Request) -> None:
    """Rate limiting for login/register (5 attempts per minute per IP)."""
    await rate_limiter.check_limit('auth', limit=5, window_seconds=60, request=request)


async def _check_api_rate_limit(request: Request) -> None:
    """Rate limiting for general API endpoints (100 requests per minute per IP)."""
    await rate_limiter.check_limit('api', limit=100, window_seconds=60, request=request)


async def _check_batch_rate_limit(request: Request) -> None:
    """Rate limiting for batch operations (10 requests per minute per IP)."""
    await rate_limiter.check_limit('batch', limit=10, window_seconds=60, request=request)


# Simple in-memory cache with TTL
class SimpleCache:
    """Simple in-memory cache with TTL (Time To Live)."""
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        async with self._lock:
            if key not in self._cache:
                return None
            
            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None
            
            return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        """Set cached value with TTL."""
        async with self._lock:
            expires_at = time.time() + ttl_seconds
            self._cache[key] = (value, expires_at)
    
    async def delete(self, key: str) -> None:
        """Delete cached value."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    async def clear(self) -> None:
        """Clear all cached values."""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> None:
        """Remove all expired entries."""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired_keys:
                del self._cache[k]


# Global cache instance
api_cache = SimpleCache()

_TOKEN_BUCKET_CAPACITY = 30.0
_TOKEN_BUCKET_REFILL_RATE = 10.0  # tokens por segundo
_rate_limiter_lock = asyncio.Lock()
_rate_buckets: Dict[str, Dict[str, float]] = {}

async def _aplicar_rate_limit(request: Request) -> None:
    chave = request.headers.get("X-Device-Id") or (request.client.host if request.client else "anonimo")
    agora = time.monotonic()
    async with _rate_limiter_lock:
        bucket = _rate_buckets.get(chave)
        if bucket is None:
            bucket = {"tokens": _TOKEN_BUCKET_CAPACITY, "ultimo": agora}
        else:
            intervalo = max(0.0, agora - bucket["ultimo"])
            bucket["tokens"] = min(
                _TOKEN_BUCKET_CAPACITY,
                bucket["tokens"] + intervalo * _TOKEN_BUCKET_REFILL_RATE,
            )
            bucket["ultimo"] = agora
        if bucket["tokens"] < 1.0:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Quota de requisicoes excedida para este dispositivo.",
                },
            )
        bucket["tokens"] -= 1.0
        _rate_buckets[chave] = bucket
    request.state.rate_key = chave


def reset_rate_limiter() -> None:
    """Limpa o estado do rate limiter (uso em testes)."""
    _rate_buckets.clear()
