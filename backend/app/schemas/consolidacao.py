"""Schemas Pydantic do extrato consolidado."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FichaResumoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome_arquivo: str
    status: str
    qtd_linhas: int
    valor_total_centavos: int
    competencia: str | None
    hospital: str | None
    coordenador: str | None
    created_at: datetime


class MedicoNoExtratoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cpf_mascarado: str
    nome: str
    qtd_aparicoes: int
    valor_total_centavos: int
    beneficiario_id: UUID | None
    beneficiario_cadastrado: bool


class ExtratoConsolidadoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    titulo: str
    cliente_id: UUID
    cliente_nome: str
    chave_agrupamento: str
    fichas: list[FichaResumoOut]
    medicos: list[MedicoNoExtratoOut]
    total_fichas: int
    total_linhas: int
    total_medicos_unicos: int
    valor_total_centavos: int
    medicos_nao_cadastrados: int


class ClienteComFichasOut(BaseModel):
    cliente_id: UUID
    nome: str
    qtd_fichas_pendentes: int


class GerarLoteConsolidadoRequest(BaseModel):
    fichas_ids: list[UUID]
    referencia: str | None = None


class GerarLoteConsolidadoResposta(BaseModel):
    lote_id: UUID
    status: str
    total_pagamentos: int
    valor_total_centavos: int


class LoteProcessadoOut(BaseModel):
    """Um lote já processado (CNAB/API) — o que saiu dos 'recebidos' e foi
    aprovado/enviado/pago. Alimenta a aba 'Processados' do Extrato."""

    lote_id: UUID
    cliente_id: UUID
    cliente_nome: str
    referencia: str | None
    competencia: str | None
    status: str
    total_pagamentos: int
    valor_total_centavos: int
    created_at: datetime
    aprovado_at: datetime | None


class ExtratoProcessadosOut(BaseModel):
    """Visão consolidada do que já foi processado, batendo com o Dashboard."""

    lotes: list[LoteProcessadoOut]
    total_lotes: int
    total_pagamentos: int
    valor_total_centavos: int


__all__ = [
    "ClienteComFichasOut",
    "ExtratoConsolidadoOut",
    "ExtratoProcessadosOut",
    "FichaResumoOut",
    "GerarLoteConsolidadoRequest",
    "GerarLoteConsolidadoResposta",
    "LoteProcessadoOut",
    "MedicoNoExtratoOut",
]
