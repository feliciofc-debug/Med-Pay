"""Schemas Pydantic para Lote e Pagamento."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.lote import StatusLote
from app.models.pagamento import ModalidadePagamento, StatusPagamento


class ClienteResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cnpj: str | None = None


class LoteResumo(BaseModel):
    """Resumo de lote para listagens (dashboard)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente: ClienteResumo
    nome_arquivo: str
    referencia: str | None
    status: StatusLote
    total_pagamentos: int
    total_validos: int
    total_corrigiveis: int
    total_bloqueados: int
    valor_total_centavos: int
    created_at: datetime
    aprovado_at: datetime | None = None


class PagamentoOut(BaseModel):
    """Pagamento (sem CPF/conta em claro)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    linha_planilha: int
    nome: str
    cpf_mascarado: str
    cpf_sugerido: str | None
    cpf_original: str | None
    banco_codigo: str | None
    conta_mascarada: str | None
    valor_centavos: int
    modalidade: ModalidadePagamento = ModalidadePagamento.TED
    chave_pix: str | None = None
    status: StatusPagamento
    codigos_erro: str | None
    mensagens_validacao: str | None


class LoteDetalhe(LoteResumo):
    """Lote com a lista completa de pagamentos."""

    pagamentos: list[PagamentoOut] = Field(default_factory=list)
    hash_conteudo: str
    hash_arquivo_cnab: str | None = None
    nome_arquivo_cnab: str | None = None


class AprovarLoteRequest(BaseModel):
    """Request de aprovação de lote (com confirmação dupla)."""

    confirmacao_total_centavos: int = Field(
        ge=0, description="Soma de centavos exibida ao operador (proteção anti-race)"
    )
    confirmacao_qtd_pagamentos: int = Field(
        ge=0, description="Quantidade de pagamentos exibida ao operador"
    )
    observacoes: str | None = Field(default=None, max_length=1000)


class AprovacaoResponse(BaseModel):
    """Resposta da aprovação — link para download do CNAB."""

    success: bool = True
    lote_id: UUID
    nome_arquivo: str
    hash_arquivo: str
    quantidade_pagamentos: int
    valor_total_centavos: int
    download_url: str


class UploadLoteResponse(BaseModel):
    """Resposta de upload bem-sucedido."""

    success: bool = True
    lote_id: UUID
    hash_conteudo: str
    total_linhas: int
    status: StatusLote
    mensagem: str
