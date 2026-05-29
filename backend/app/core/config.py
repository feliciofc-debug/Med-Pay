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
    # Lista explícita de origens (separadas por vírgula).
    CORS_ORIGINS: str = "http://localhost:5173"
    # Regex adicional pra matchar qualquer preview deploy (ex.: Vercel cria
    # subdomínios novos a cada PR/branch como med-pay-91t6.vercel.app).
    # Default: aceita localhost dev + qualquer *.vercel.app do projeto.
    CORS_ORIGIN_REGEX: str = (
        r"^(http://localhost:\d+|https://([a-z0-9-]+\.)*vercel\.app)$"
    )

    # ===== Upload =====
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".xlsx", ".xls", ".csv")

    # ===== OCR =====
    # Chave gratuita: https://ocr.space/ocrapi (25k páginas/mês).
    # Sem ela, o módulo de fichas escaneadas fica indisponível —
    # a API retorna 503 OCR_INDISPONIVEL ao tentar usar.
    OCR_SPACE_API_KEY: str | None = None
    OCR_MAX_FILE_MB: int = 5  # Limite do plano free do OCR.space

    # ===== Jarvis (Groq + WhatsApp via Wuzapi) =====
    # Groq: 14.4k req/dia grátis em modelos grandes — suficiente pro Jarvis.
    # https://console.groq.com/keys
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TEMPERATURE: float = 0.2
    GROQ_MAX_TOKENS: int = 1024

    # Modelo multimodal (vision) — usado pelo parser de fichas
    # pra ler IMAGEM/PDF da ficha e devolver JSON estruturado direto,
    # sem depender do OCR.space + regex. Llama 4 Scout é gratuito no
    # plano free do Groq e foi o mais preciso nos testes em fichas
    # de plantão (tabelas, manuscritos parciais, carimbos).
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_VISION_MAX_TOKENS: int = 4096
    GROQ_VISION_TIMEOUT_S: int = 90

    # Quando True, fichas usam Groq Vision como caminho principal e
    # caem no OCR.space + regex só se Groq falhar.
    # Quando False, ignora Groq e usa direto OCR.space.
    # (Mesmo com True, se GROQ_API_KEY estiver vazio, cai no OCR.space.)
    USAR_GROQ_VISION: bool = True

    # Wuzapi (WhatsApp não oficial, rodado em VPS Contabo)
    WUZAPI_URL: str | None = None  # ex: http://seuvps:8080

    # Token admin do servidor Wuzapi (usado em endpoints /admin/*).
    # Opcional se WUZAPI_INSTANCE_TOKEN ja estiver configurado.
    WUZAPI_ADMIN_TOKEN: str | None = None

    # ⭐ JEITO RECOMENDADO (e que funciona em 100% dos casos):
    # Crie um user/sessao manualmente no servidor Wuzapi e cole aqui o token.
    # O Med-Pay vai usar essa sessao diretamente, sem precisar criar/listar
    # nada via /admin/users (que muda de schema entre forks).
    WUZAPI_INSTANCE_TOKEN: str | None = None
    # Nome/ID do user no Wuzapi (para identificacao). Se nao setar,
    # geramos um automatico ("medpag-jarvis").
    WUZAPI_INSTANCE_ID: str | None = None

    # Nome do header HTTP onde mandamos o token. O Wuzapi oficial usa
    # "Token", mas forks customizados (ex: AMZ Ofertas) usam "Authorization"
    # em endpoints admin. Default = mandamos AMBOS, entao essa flag e
    # so pra forks bem exoticos.
    WUZAPI_AUTH_HEADER: str = "Token"

    # Segredo compartilhado pra autenticar webhooks vindos do Wuzapi
    # (configurado no provisionamento, header X-Webhook-Secret).
    WUZAPI_WEBHOOK_SECRET: str | None = None

    # Janela máxima de histórico que o Jarvis carrega como contexto
    # (mensagens das últimas N horas, máximo M mensagens).
    # Aumentado pra ter memoria conversacional decente — um socio precisa
    # lembrar do que foi falado mais cedo no dia.
    JARVIS_HISTORICO_HORAS: int = 24
    JARVIS_HISTORICO_MAX: int = 25

    # ===== Negócio =====
    # Range típico de valores (em centavos) — fora disso é "suspeito"
    VALOR_MIN_CENTAVOS: int = 100  # R$ 1,00
    VALOR_MAX_CENTAVOS: int = 100_000_00  # R$ 100.000,00

    # ===== Asaas (cobrança recorrente das assinaturas MedPag) =====
    # Crie a chave em https://www.asaas.com (sandbox: sandbox.asaas.com).
    # Sem ASAAS_API_KEY o serviço fica em "modo desligado" — endpoints
    # de cobrança retornam 503 ASAAS_INDISPONIVEL e o frontend mostra
    # banner pedindo configuração.
    ASAAS_API_KEY: str | None = None
    ASAAS_BASE_URL: str = "https://sandbox.asaas.com/api/v3"  # prod: https://api.asaas.com/api/v3
    ASAAS_WEBHOOK_TOKEN: str | None = None  # validado no header asaas-access-token
    ASAAS_DEFAULT_BILLING_TYPE: Literal["BOLETO", "CREDIT_CARD", "PIX", "UNDEFINED"] = (
        "UNDEFINED"
    )

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
