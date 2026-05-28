"""Schemas Pydantic do log de Auditoria."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    user_nome: str | None = None
    user_email: str | None = None
    acao: str
    entidade_tipo: str | None
    entidade_id: UUID | None
    detalhes: dict[str, Any] | None
    hash_relacionado: str | None
    ip_address: str | None
    mensagem: str | None
    created_at: datetime


class AuditoriaPage(BaseModel):
    items: list[AuditoriaOut]
    total: int
    page: int
    per_page: int
    total_pages: int


__all__ = ["AuditoriaOut", "AuditoriaPage"]
