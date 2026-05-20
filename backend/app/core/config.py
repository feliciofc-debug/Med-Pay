"""Configurações centralizadas do MedPag.

Todas as configurações vêm de variáveis de ambiente, carregadas via Pydantic Settings.
NUNCA hardcode valores aqui.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== Ambiente =====
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ===== Banco de dados =====
    DATABASE_URL: str = Field(
        ...,
        description="URL do PostgreSQL no formato postgresql+asyncpg://...",
    )
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_ECHO: bool = False  # True só pra debug local de SQL

    # ===== Redis =====
    REDIS_URL: str = Field(..., description="URL do Redis")

    # ===== Segurança =====
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Chave secreta para assinatura JWT (mínimo 32 chars)",
    )
    ENCRYPTION_KEY: str = Field(
        ...,
        description="Chave Fernet para criptografia de campos sensíveis (44 chars base64)",
    )

    # ===== JWT =====
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ===== CORS =====
    CORS_ORIGINS: str = "http://localhost:5173"

    # ===== Upload =====
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".xlsx", ".xls", ".csv")

    # ===== Negócio =====
    # Range típico de valores (em centavos) — fora disso é "suspeito"
    VALOR_MIN_CENTAVOS: int = 100  # R$ 1,00
    VALOR_MAX_CENTAVOS: int = 100_000_00  # R$ 100.000,00

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Normaliza a URL do PostgreSQL para o driver assíncrono.

        Provedores como Render/Heroku/Railway/Supabase entregam a URL no formato
        `postgres://...` ou `postgresql://...`. O SQLAlchemy assíncrono precisa
        do prefixo `postgresql+asyncpg://`. Esta conversão é feita aqui pra que
        a mesma variável de ambiente funcione em qualquer plataforma.
        """
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://") and "+" not in v.split("://", 1)[0]:
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def normalize_redis_url(cls, v: str) -> str:
        """Normaliza URL do Redis. Aceita rediss:// (TLS) e redis://."""
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Aceita string separada por vírgula."""
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna CORS_ORIGINS como lista."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância única (singleton) das configurações."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
