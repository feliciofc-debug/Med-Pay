"""Schemas de Configuração Operacional per-tenant."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConfigOperacaoOut(BaseModel):
    """Configuração operacional de um cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    dia_fechamento: int
    fuso_horario: str
    modalidade_preferida: str
    logo_url: str | None
    cor_primaria: str


class AtualizarConfigOperacaoRequest(BaseModel):
    """Atualiza só os campos enviados (PATCH semântico)."""

    dia_fechamento: int | None = Field(None, ge=0, le=31)
    fuso_horario: str | None = Field(None, max_length=50)
    modalidade_preferida: Literal["PIX", "TED", "CC", "OUTRO"] | None = None
    logo_url: str | None = Field(None, max_length=500)
    cor_primaria: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


__all__ = ["AtualizarConfigOperacaoRequest", "ConfigOperacaoOut"]
