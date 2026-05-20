"""Criptografia de campos sensíveis (CPF, conta bancária).

Usa Fernet (AES-128 + HMAC) da biblioteca `cryptography`. Cada campo é
criptografado individualmente e armazenado em coluna BYTEA do Postgres.

REGRAS:
- CPF e conta bancária NUNCA são armazenados em plaintext
- A chave de criptografia vem de ENCRYPTION_KEY (variável de ambiente)
- Em produção, considere rotação de chave via MultiFernet
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache
def _get_cipher() -> Fernet:
    """Retorna a instância Fernet (cacheada)."""
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt(plaintext: str) -> bytes:
    """Criptografa uma string. Retorna bytes pra armazenar em BYTEA.

    Args:
        plaintext: Texto em claro (CPF, conta, etc)

    Returns:
        Bytes criptografados

    Raises:
        ValueError: Se plaintext for vazio
    """
    if not plaintext:
        raise ValueError("Não é possível criptografar string vazia")
    return _get_cipher().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Descriptografa bytes vindos do banco.

    Args:
        ciphertext: Bytes criptografados (vindos de coluna BYTEA)

    Returns:
        String em claro

    Raises:
        InvalidToken: Se os bytes não são um token Fernet válido
    """
    return _get_cipher().decrypt(ciphertext).decode("utf-8")


def hash_for_lookup(plaintext: str) -> str:
    """Gera hash determinístico para buscar registros sem descriptografar.

    Útil para verificar "este CPF já existe no banco" sem expor o CPF real.
    NÃO use isso pra autenticação — é só pra busca/duplicação.

    Args:
        plaintext: String pra hashear (já deve estar normalizada/limpa)

    Returns:
        Hash SHA-256 em hex (64 chars)
    """
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def mask_cpf(cpf_limpo: str) -> str:
    """Mascara CPF para exibição em logs e telas não autorizadas.

    Formato: XXX.XXX.XXX-12 (mostra apenas os 2 últimos dígitos)

    Conforme LGPD: CPF NUNCA aparece em plaintext em logs ou telas
    onde o usuário não tem permissão explícita.
    """
    if not cpf_limpo or len(cpf_limpo) < 4:
        return "***"
    return f"XXX.XXX.XXX-{cpf_limpo[-2:]}"


def mask_conta(conta_limpa: str) -> str:
    """Mascara número de conta para exibição.

    Formato: ****1234 (mostra apenas os 4 últimos dígitos)
    """
    if not conta_limpa or len(conta_limpa) < 5:
        return "****"
    return f"****{conta_limpa[-4:]}"
