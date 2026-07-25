"""Shared utilities for API routers."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import time
from collections import defaultdict
from typing import Any, Dict, List

import structlog
from fastapi import HTTPException, Request, status
from configuracao import carregar_configuracao

logger = structlog.get_logger(__name__)

config = carregar_configuracao()
DB_PATH = config.db_path

DEFAULT_PERFIL = "medio"
APP_VERSION = "1.0.0"
APP_START_TIME = time.time()

def _redes_confiaveis() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Redes de onde um X-Forwarded-For pode ser acreditado.

    Configurável por TRUSTED_PROXIES (CIDRs separados por vírgula). O default
    são as faixas privadas, porque o Caddy fala com o app pela rede interna do
    Docker.
    """
    bruto = os.getenv("TRUSTED_PROXIES", "").strip()
    if bruto:
        redes = []
        for item in bruto.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                redes.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                logger.warning("trusted_proxy_invalido", valor=item)
        return redes
    return [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]


def ip_do_cliente(request: Request) -> str:
    """IP real do cliente, considerando o proxy reverso.

    O rate limit usava `request.client.host` direto. Atrás do Caddy isso é
    SEMPRE o IP do proxy, então todos os usuários caíam no mesmo balde: um
    único cliente estourava o limite de todo mundo (negação de serviço trivial)
    e, no caminho de ingestão, bastava trocar o X-Device-Id para contornar.

    O X-Forwarded-For só é acreditado quando o peer imediato é um proxy
    confiável — senão qualquer cliente forjaria o header e escaparia do limite.
    Por isso a porta 8000 não deve ser exposta publicamente em produção (só
    80/443 no firewall, ver GUIA_BUILD_DEPLOYMENT.md).
    """
    peer = request.client.host if request.client else None
    if not peer:
        return "desconhecido"

    encaminhado = request.headers.get("X-Forwarded-For", "")
    if encaminhado:
        try:
            ip_peer = ipaddress.ip_address(peer)
            if any(ip_peer in rede for rede in _redes_confiaveis()):
                primeiro = encaminhado.split(",")[0].strip()
                if primeiro:
                    return primeiro
        except ValueError:
            pass
    return peer


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
        client_ip = ip_do_cliente(request)
        now = time.time()

        async with self._lock:
            # Clean old attempts
            if client_ip in self._attempts[key]:
                self._attempts[key][client_ip] = [
                    ts for ts in self._attempts[key][client_ip]
                    if now - ts < window_seconds
                ]

            # Descarta chaves que ficaram vazias. O dict é indexado por IP e
            # nunca era limpo: com IPs reais (e não mais só o do proxy) ele
            # cresceria indefinidamente, virando vetor de exaustão de memória.
            self._expirar_ociosos(key, now, window_seconds)

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
    
    def _expirar_ociosos(self, key: str, now: float, window_seconds: int) -> None:
        """Remove IPs sem tentativas dentro da janela (chamado com o lock)."""
        balde = self._attempts.get(key)
        if not balde:
            return
        ociosos = [
            ip for ip, marcas in balde.items()
            if not marcas or now - marcas[-1] >= window_seconds
        ]
        for ip in ociosos:
            del balde[ip]

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

# Configuráveis: uma instalação com muitos ESP32 atrás do mesmo NAT pode
# precisar de mais folga, já que o balde é por IP (ver abaixo).
_TOKEN_BUCKET_CAPACITY = float(os.getenv("INGESTAO_BURST", "30"))
_TOKEN_BUCKET_REFILL_RATE = float(os.getenv("INGESTAO_RPS", "10"))  # tokens por segundo
_rate_limiter_lock = asyncio.Lock()
_rate_buckets: Dict[str, Dict[str, float]] = {}


def _expirar_baldes(agora: float) -> None:
    """Descarta baldes cheios e parados (chamado com o lock).

    Um balde que ja recarregou ate a capacidade nao carrega informacao alguma:
    manter a entrada so consome memoria.
    """
    if len(_rate_buckets) < 1000:
        return
    tempo_para_encher = _TOKEN_BUCKET_CAPACITY / max(_TOKEN_BUCKET_REFILL_RATE, 0.001)
    for ip in [
        ip for ip, b in _rate_buckets.items()
        if agora - b["ultimo"] > tempo_para_encher
    ]:
        del _rate_buckets[ip]


async def _aplicar_rate_limit(request: Request) -> None:
    # A chave era o X-Device-Id, que o próprio cliente escolhe: bastava
    # rotacionar o header para ganhar um balde novo e furar o limite. O
    # fallback (request.client.host) também não servia, porque atrás do Caddy é
    # sempre o IP do proxy — todos os dispositivos num único balde.
    #
    # Agora a chave é o IP real (ip_do_cliente), que o cliente não controla. O
    # device_id fica só como contexto de log.
    chave = ip_do_cliente(request)
    agora = time.monotonic()
    async with _rate_limiter_lock:
        # Sem isto o dict cresce por IP e nunca encolhe.
        _expirar_baldes(agora)
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
            logger.warning(
                "ingestao_rate_limited",
                ip=chave,
                device_id=request.headers.get("X-Device-Id"),
            )
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Quota de requisicoes excedida para esta origem.",
                },
            )
        bucket["tokens"] -= 1.0
        _rate_buckets[chave] = bucket
    request.state.rate_key = chave


def reset_rate_limiter() -> None:
    """Limpa o estado do rate limiter (uso em testes)."""
    _rate_buckets.clear()
