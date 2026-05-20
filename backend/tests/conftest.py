"""Fixtures globais do pytest.

Carregamos variáveis de ambiente fake antes que `app.core.config` seja
importado. Isso permite rodar testes unitários (validators, crypto, etc)
sem precisar de banco real.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet


def _set_test_env() -> None:
    """Define variáveis de ambiente seguras para os testes."""
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://medpag:medpag_dev@localhost:5432/medpag_test",
    )
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault(
        "SECRET_KEY",
        "test_secret_key_at_least_32_chars_long_for_pytest_only",
    )
    # Chave Fernet determinística para testes (NUNCA usar em produção)
    os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ.setdefault("ENVIRONMENT", "development")


_set_test_env()


@pytest.fixture
def cpf_valido() -> str:
    """CPF válido conhecido (não real, gerado pelo algoritmo)."""
    return "11144477735"


@pytest.fixture
def cpf_valido_com_zero() -> str:
    """CPF válido começando com 0 (testa correção de zero perdido pelo Excel)."""
    return "04223830000"


@pytest.fixture
def fernet_key() -> Iterator[str]:
    """Gera uma nova chave Fernet pra testes que precisam isolar criptografia."""
    yield Fernet.generate_key().decode()
