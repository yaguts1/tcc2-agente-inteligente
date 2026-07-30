"""JWT Authentication Utilities."""
from datetime import datetime, timedelta, UTC
from jose import jwt, JWTError
import os
import secrets
import structlog

logger = structlog.get_logger(__name__)

# Configuration
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_DEV_FALLBACK_SECRET = "dev-only-insecure-secret-do-not-use-in-production"

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    if _ENVIRONMENT == "production":
        raise RuntimeError(
            "JWT_SECRET_KEY nao configurado. Defina essa variavel de ambiente "
            "antes de rodar com ENVIRONMENT=production."
        )
    logger.warning(
        "jwt_secret_key_dev_fallback",
        motivo="JWT_SECRET_KEY nao definido; usando segredo de desenvolvimento inseguro",
    )
    SECRET_KEY = _DEV_FALLBACK_SECRET

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours
# Fonte unica do TTL da sessao: os cookies de login precisam expirar junto com
# o JWT (antes o valor 8h estava repetido em varios set_cookie e podia
# dessincronizar do token).
ACCESS_TOKEN_EXPIRE_SECONDS = ACCESS_TOKEN_EXPIRE_MINUTES * 60


def ambiente_atual() -> str:
    """Ambiente de execucao, lido dinamicamente.

    `_ENVIRONMENT` acima e resolvido no import (necessario para falhar cedo sem
    JWT_SECRET_KEY); aqui a leitura e por chamada para que testes e cenarios de
    runtime possam alternar o ambiente.
    """
    return os.getenv("ENVIRONMENT", "development").lower()


def em_producao() -> bool:
    return ambiente_atual() == "production"

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    # datetime.utcnow() é deprecado no Python 3.12+; usar aware UTC.
    agora = datetime.now(UTC)
    expire = agora + expires_delta if expires_delta else agora + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # `jti` e `iat` existem para permitir revogação:
    #  - jti identifica ESTE token, para o logout encerrar só aquela sessão;
    #  - iat data a emissão, para o corte `tokens_validos_apos` invalidar de
    #    uma vez todas as sessões anteriores (troca de senha, saída forçada).
    # Sem eles o token era irrevogável: valia as 8h inteiras, acontecesse o
    # que acontecesse.
    to_encode.update({
        "exp": expire,
        "iat": agora,
        "jti": secrets.token_urlsafe(16),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
