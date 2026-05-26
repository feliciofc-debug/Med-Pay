"""Schemas Pydantic do cadastro de beneficiários (prestadores).

Cobrem:
    - CRUD UI (criar, atualizar, listar, detalhar)
    - Importação de planilha (preview com erros + confirmação)
    - Aprovação/desativação
    - Lookup interno (usado pelo pipeline de fichas)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.beneficiario import (
    OrigemCadastroBeneficiario,
    StatusBeneficiario,
)


# ============================================================
# Output / detalhes
# ============================================================


class BeneficiarioOut(BaseModel):
    """Beneficiário visível na UI (sem campos criptografados)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    nome: str
    cpf_mascarado: str

    crm: str | None = None
    categoria: str | None = None
    especialidade: str | None = None

    email: str | None = None
    telefone: str | None = None

    banco_codigo: str | None = None
    agencia_mascarada: str | None = None
    conta_mascarada: str | None = None
    pix_tipo: str | None = None
    pix_chave_mascarada: str | None = None

    valor_padrao_centavos: int | None = None

    status: StatusBeneficiario
    origem_cadastro: OrigemCadastroBeneficiario
    observacoes: str | None = None

    total_pagamentos: int
    valor_medio_centavos: int
    valor_min_centavos: int
    valor_max_centavos: int
    ultimo_pagamento_at: datetime | None = None

    ativo: bool
    created_at: datetime
    updated_at: datetime


class BeneficiarioListResponse(BaseModel):
    """Lista paginada."""

    items: list[BeneficiarioOut]
    total: int
    page: int
    per_page: int
    total_pages: int


# ============================================================
# Input — criação manual e edição
# ============================================================


class BeneficiarioBase(BaseModel):
    """Campos que o admin pode digitar na UI."""

    nome: str = Field(min_length=2, max_length=255)
    cpf: str = Field(min_length=11, max_length=20, description="CPF com ou sem máscara")

    crm: str | None = Field(default=None, max_length=40)
    categoria: str | None = Field(default=None, max_length=80)
    especialidade: str | None = Field(default=None, max_length=80)

    email: str | None = Field(default=None, max_length=255)
    telefone: str | None = Field(default=None, max_length=20)

    banco_codigo: str | None = Field(default=None, max_length=3)
    agencia: str | None = Field(default=None, max_length=10)
    conta: str | None = Field(default=None, max_length=20)

    pix_tipo: str | None = Field(default=None, max_length=20)
    pix_chave: str | None = Field(default=None, max_length=120)

    valor_padrao_centavos: int | None = Field(default=None, ge=0)
    observacoes: str | None = Field(default=None, max_length=1024)


class BeneficiarioCreateRequest(BeneficiarioBase):
    """Cadastro novo (manual via UI)."""

    cliente_id: UUID
    status: StatusBeneficiario = StatusBeneficiario.ATIVO


class BeneficiarioUpdateRequest(BaseModel):
    """Edição parcial (PATCH). Todos os campos opcionais."""

    nome: str | None = Field(default=None, min_length=2, max_length=255)
    crm: str | None = Field(default=None, max_length=40)
    categoria: str | None = Field(default=None, max_length=80)
    especialidade: str | None = Field(default=None, max_length=80)

    email: str | None = Field(default=None, max_length=255)
    telefone: str | None = Field(default=None, max_length=20)

    banco_codigo: str | None = Field(default=None, max_length=3)
    agencia: str | None = Field(default=None, max_length=10)
    conta: str | None = Field(default=None, max_length=20)

    pix_tipo: str | None = Field(default=None, max_length=20)
    pix_chave: str | None = Field(default=None, max_length=120)

    valor_padrao_centavos: int | None = Field(default=None, ge=0)
    observacoes: str | None = Field(default=None, max_length=1024)
    status: StatusBeneficiario | None = None


# ============================================================
# Importação de planilha
# ============================================================


class LinhaImportPreview(BaseModel):
    """Uma linha do preview de importação — antes da confirmação."""

    linha_planilha: int = Field(description="Número da linha na planilha (1-indexed)")
    nome: str | None = None
    cpf_mascarado: str | None = None
    crm: str | None = None
    email: str | None = None
    telefone: str | None = None
    banco_codigo: str | None = None
    agencia_mascarada: str | None = None
    conta_mascarada: str | None = None
    pix_tipo: str | None = None
    pix_chave_mascarada: str | None = None
    valor_padrao_centavos: int | None = None

    # Status da linha
    status: str = Field(
        description="OK | DUPLICADO | ERRO | ATUALIZA — o que vai acontecer ao confirmar"
    )
    erros: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # Se for DUPLICADO/ATUALIZA, ID do beneficiario existente
    beneficiario_id_existente: UUID | None = None


class ImportPreviewResponse(BaseModel):
    """Resultado de chamar /import/preview — usuário revisa antes de confirmar."""

    cliente_id: UUID
    total_linhas: int
    qtd_ok: int
    qtd_duplicados: int  # mesmo CPF + mesmo dado bancário
    qtd_atualiza: int    # mesmo CPF, dados diferentes
    qtd_erro: int
    linhas: list[LinhaImportPreview]
    # Token opaco usado pra confirmar a importação sem reupload do arquivo
    token: str


class ImportConfirmRequest(BaseModel):
    """Confirma importação previamente analisada."""

    token: str = Field(description="Token devolvido pelo /import/preview")
    # Política para linhas que dão "ATUALIZA":
    #   IGNORAR — mantém o cadastro atual, ignora a linha
    #   ATUALIZAR — sobrescreve o cadastro com os dados da planilha
    politica_atualizacao: str = Field(default="IGNORAR")


class ImportConfirmResponse(BaseModel):
    """Resumo do que foi efetivamente importado."""

    qtd_criados: int
    qtd_atualizados: int
    qtd_ignorados: int
    qtd_erros: int


__all__ = [
    "BeneficiarioCreateRequest",
    "BeneficiarioListResponse",
    "BeneficiarioOut",
    "BeneficiarioUpdateRequest",
    "ImportConfirmRequest",
    "ImportConfirmResponse",
    "ImportPreviewResponse",
    "LinhaImportPreview",
]
