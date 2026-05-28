"""Schemas Pydantic do signup self-service."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.plano import StatusAssinatura
from app.schemas.auth import UserOut


class SignupRequest(BaseModel):
    """Payload do wizard de onboarding."""

    plano_slug: str = Field(..., description="Slug do plano (ex: 'inicial')")
    nome_empresa: str = Field(..., min_length=2, max_length=255)
    cnpj: str | None = Field(None, description="14 dígitos (pode vir formatado)")
    email_contato: str | None = None
    telefone: str | None = None

    admin_nome: str = Field(..., min_length=2, max_length=255)
    admin_email: str = Field(..., max_length=255)
    admin_senha: str = Field(..., min_length=8, max_length=128)


class SignupResposta(BaseModel):
    """Resposta após criar cliente + user. Inclui tokens pra login direto."""

    cliente_id: UUID
    nome_empresa: str
    status_assinatura: StatusAssinatura
    trial_termina_em: datetime | None

    user: UserOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


__all__ = ["SignupRequest", "SignupResposta"]
