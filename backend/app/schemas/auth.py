"""Schemas de autenticação."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class UserOut(BaseModel):
    """Usuário (representação pública, sem senha)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    nome: str
    role: UserRole
    ativo: bool
    created_at: datetime
    last_login_at: datetime | None = None
