"""Schemas Pydantic do módulo Equipe Flex."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# Membros
# ============================================================


class MembroEquipeIn(BaseModel):
    """Payload para criar/editar um membro."""

    nome: str = Field(..., min_length=2, max_length=200)
    cpf: str = Field(..., description="CPF com 11 dígitos (sem pontuação ou com)")
    crm_ou_registro: str | None = None
    chave_pix: str | None = None
    banco_codigo: str | None = None
    agencia: str | None = None
    conta: str | None = None
    ativo: bool = True

    @field_validator("cpf")
    @classmethod
    def _limpar_cpf(cls, v: str) -> str:
        digitos = "".join(c for c in v if c.isdigit())
        if len(digitos) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return digitos


class MembroEquipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cpf: str
    crm_ou_registro: str | None
    chave_pix: str | None
    banco_codigo: str | None
    agencia: str | None
    conta: str | None
    ativo: bool


# ============================================================
# Equipe
# ============================================================


class ClienteResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cnpj: str | None = None


class EquipeIn(BaseModel):
    cliente_id: UUID
    nome: str = Field(..., min_length=2, max_length=120)
    categoria: str = Field("Plantonista", min_length=2, max_length=80)
    valor_hora_centavos: int = Field(..., ge=0)
    ativa: bool = True
    observacoes: str | None = None


class EquipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente: ClienteResumo
    nome: str
    categoria: str
    valor_hora_centavos: int
    ativa: bool
    observacoes: str | None
    qtd_membros: int = 0
    qtd_membros_ativos: int = 0
    membros: list[MembroEquipeOut] = []
    created_at: datetime


# ============================================================
# Fechamentos
# ============================================================


class FechamentoIn(BaseModel):
    """Cria um fechamento mensal (preview ou efetivo).

    Quando `confirmar=False`, o backend só CALCULA os valores e devolve
    o preview, sem persistir. Quando `confirmar=True`, persiste e
    gera o lote de pagamento.
    """

    equipe_id: UUID
    competencia: str = Field(
        ..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Formato YYYY-MM"
    )
    horas_total: int = Field(..., gt=0, le=10000)
    origem: str = Field("DIGITACAO", pattern=r"^(DIGITACAO|FICHA_OCR)$")
    ficha_id: UUID | None = None
    confirmar: bool = False
    observacoes: str | None = None


class FechamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None  # None quando é só preview
    equipe_id: UUID
    competencia: str
    horas_total: int
    valor_hora_centavos: int
    valor_bruto_centavos: int
    desconto_medpag_centavos: int
    valor_liquido_centavos: int
    qtd_membros: int
    valor_por_membro_centavos: int
    origem: str
    ficha_id: UUID | None
    lote_id: UUID | None
    aprovado_at: datetime | None
    observacoes: str | None
    created_at: datetime | None = None


__all__ = [
    "ClienteResumo",
    "EquipeIn",
    "EquipeOut",
    "FechamentoIn",
    "FechamentoOut",
    "MembroEquipeIn",
    "MembroEquipeOut",
]
