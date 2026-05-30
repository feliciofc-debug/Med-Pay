"""Schemas de autenticação."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.cliente import ModoPagamento, TipoCliente
from app.models.user import UserRole


class LoginRequest(BaseModel):
    """Request de login."""

    email: EmailStr
    password: str = Field(min_length=1, description="Senha em claro (será verificada)")


class TokenPair(BaseModel):
    """Par de tokens emitido após login bem-sucedido."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Segundos até o access_token expirar")


class RefreshRequest(BaseModel):
    """Request de refresh token."""

    refresh_token: str


class ClienteMini(BaseModel):
    """Cliente mínimo embarcado no UserOut para contexto multi-tenant.

    Carrega os 3 eixos da engenharia de modelos de negócio pro frontend
    derivar menu/dashboard sem hardcode:
    - `tipo` (Eixo 1: quem é o cliente)
    - `modo_pagamento` (Eixo 3: como o repasse sai)
    - `features` (Eixo 2: dict resolvido de capacidades ligadas)
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    tipo: TipoCliente = TipoCliente.HOSPITAL
    modo_pagamento: ModoPagamento = ModoPagamento.CNAB_BANCARIO
    features: dict[str, Any] = Field(default_factory=dict)


class UserOut(BaseModel):
    """Usuário (representação pública, sem senha)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    nome: str
    role: UserRole
    ativo: bool
    cliente_id: UUID | None = None
    cliente: ClienteMini | None = None
    created_at: datetime
    last_login_at: datetime | None = None
