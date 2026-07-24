"""JWT Authentication Utilities."""
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
import os
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

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
