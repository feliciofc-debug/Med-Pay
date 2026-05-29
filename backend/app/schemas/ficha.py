"""Schemas Pydantic para FichaPlantao (módulo de OCR)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.ficha_plantao import StatusFicha


class ClienteResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cnpj: str | None = None


class LinhaExtraidaSchema(BaseModel):
    """Uma linha de pagamento candidata extraída pelo OCR + parser."""

    cpf: str | None = None
    nome: str | None = None
    valor_centavos: int | None = Field(default=None, ge=0)
    qtd_plantoes: int | None = Field(default=None, ge=0)
    horas: int | None = Field(default=None, ge=0)
    especialidade: str | None = None
    banco_codigo: str | None = None
    agencia: str | None = None
    conta: str | None = None
    chave_pix: str | None = None
    linha_origem: str = ""
    avisos: list[str] = Field(default_factory=list)

    # Calculados a partir dos campos acima — backend preenche, frontend só lê.
    # Indica se a linha tem todos os essenciais (CPF + nome + valor +
    # PIX ou banco completo) pra virar pagamento.
    essenciais_faltantes: list[str] = Field(default_factory=list)
    esta_pronta: bool = False


class FichaResumo(BaseModel):
    """Resumo da ficha (lista)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente: ClienteResumo
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    status: StatusFicha
    paginas_ocr: int
    total_linhas: int
    valor_total_centavos: int
    mensagem_erro: str | None
    lote_gerado_id: UUID | None
    created_at: datetime
    revisado_at: datetime | None


class FichaDetalhe(FichaResumo):
    """Detalhe da ficha com texto OCR + linhas parseadas + metadados."""

    texto_ocr: str | None
    linhas_extraidas: list[LinhaExtraidaSchema]
    metadados: dict[str, Any] | None


class AtualizarLinhasRequest(BaseModel):
    """Payload do PUT /fichas/{id}/linhas."""

    linhas: list[LinhaExtraidaSchema]
    metadados: dict[str, Any] | None = None


class ConverterEmLoteResponse(BaseModel):
    """Retorno do POST /fichas/{id}/converter."""

    lote_id: UUID
    qtd_pagamentos: int


__all__ = [
    "AtualizarLinhasRequest",
    "ConverterEmLoteResponse",
    "FichaDetalhe",
    "FichaResumo",
    "LinhaExtraidaSchema",
]
