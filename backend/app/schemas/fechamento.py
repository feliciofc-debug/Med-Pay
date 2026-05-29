"""Schemas Pydantic do fechamento de período."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.fechamento_periodo import StatusFechamento


class TrancarPeriodoRequest(BaseModel):
    """Payload pra trancar um período."""

    ano: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)
    observacoes: str | None = Field(default=None, max_length=500)


class PreviewFechamentoRequest(BaseModel):
    """Preview (não persiste) do que entraria no fechamento."""

    ano: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)


class _UserMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    email: str


class _ClienteMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str


class _LoteMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str


class FechamentoOut(BaseModel):
    """Representação de um fechamento."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    cliente: _ClienteMini | None = None
    ano: int
    mes: int
    competencia: str  # virtual property
    status: StatusFechamento
    total_centavos: int
    qtd_fichas: int
    qtd_medicos: int
    qtd_linhas: int
    lote_id: UUID | None = None
    lote: _LoteMini | None = None
    trancado_em: datetime | None = None
    trancado_por: _UserMini | None = None
    reaberto_em: datetime | None = None
    reaberto_por: _UserMini | None = None
    observacoes: str | None = None
    created_at: datetime
    updated_at: datetime


class FechamentoListResponse(BaseModel):
    fechamentos: list[FechamentoOut]
    total: int


class ReabrirFechamentoResponse(BaseModel):
    fechamento: FechamentoOut
    mensagem: str = "Fechamento reaberto. Fichas podem ser alteradas novamente."


class GerarLoteResponse(BaseModel):
    fechamento: FechamentoOut
    lote_id: UUID
    mensagem: str = (
        "Lote gerado a partir do fechamento. "
        "Veja em 'Lotes' pra aprovar e baixar CNAB/planilha PIX."
    )
