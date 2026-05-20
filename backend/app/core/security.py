"""Segurança: hashing de senha e JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt aceita no máximo 72 bytes; senhas maiores são truncadas com aviso.
# Em vez disso, fazemos pre-hash com SHA-256 quando excede 72 bytes,
# para preservar entropia. Boa prática usada em DBs modernos.
_BCRYPT_MAX_BYTES = 72


def _normalize_password(plain_password: str) -> bytes:
    """Codifica senha em UTF-8 e pre-hasheia se exceder 72 bytes.

    Usar pre-hash mantém entropia de senhas longas sem o limite do bcrypt.
    """
    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > _BCRYPT_MAX_BYTES:
        import hashlib

        return hashlib.sha256(pwd_bytes).hexdigest().encode("utf-8")
    return pwd_bytes


def hash_password(plain_password: str) -> str:
    """Gera hash bcrypt da senha (cost 12)."""
    pwd = _normalize_password(plain_password)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se senha em claro bate com o hash."""
    pwd = _normalize_password(plain_password)
    try:
        return bcrypt.checkpw(pwd, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: UUID,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Cria um JWT de acesso.

    Args:
        user_id: ID do usuário (vai pro claim `sub`)
        extra_claims: Claims adicionais (role, permissions, etc)

    Returns:
        Token JWT como string
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Cria um JWT de refresh (validade mais longa)."""
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica e valida um JWT.

    Raises:
        JWTError: Se o token for inválido ou expirado
    """
    return jwt.decode(  # type: ignore[no-any-return]
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
