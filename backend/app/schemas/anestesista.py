"""Schemas do fluxo de autoatendimento do médico anestesista.

Endpoints públicos (com auth leve por CRM) e endpoints administrativos
(autenticação tradicional de operador BPO).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.lancamento_servico import StatusLancamento


# ============================================================
# Auth leve por CRM (público)
# ============================================================


class CrmLoginRequest(BaseModel):
    """Request de início de sessão por CRM (sem senha por enquanto).

    O médico digita o CRM (ex.: "12345/SP"). O backend tenta encontrar um
    Beneficiario ATIVO em algum cliente que tenha esse CRM. Se único,
    emite um token de curta duração. Se ambíguo, retorna erro CRM_AMBIGUO
    e o front pede pra escolher o cliente.
    """

    crm: str = Field(min_length=3, max_length=40, description="CRM do médico")
    cliente_id: UUID | None = Field(
        default=None,
        description=(
            "Opcional: se o CRM existe em mais de um cliente, especificar "
            "o cliente_id desambigua."
        ),
    )


class MedicoOut(BaseModel):
    """Identidade do médico devolvida ao front após o login por CRM."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    crm: str | None
    especialidade: str | None
    cliente_id: UUID
    cliente_nome: str


class CrmLoginResponse(BaseModel):
    """Resposta de login por CRM."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    medico: MedicoOut


# ============================================================
# Códigos de serviço
# ============================================================


class CodigoServicoOut(BaseModel):
    """Código de serviço (visão do médico ao buscar)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo: str
    descricao: str
    valor_centavos: int
    categoria: str | None = None
    porte: str | None = None


class CodigoServicoCreate(BaseModel):
    """Admin: cria um código de serviço."""

    codigo: str = Field(min_length=1, max_length=40)
    descricao: str = Field(min_length=1, max_length=500)
    valor_centavos: int = Field(ge=0)
    categoria: str | None = Field(default=None, max_length=120)
    porte: str | None = Field(default=None, max_length=40)
    observacoes: str | None = Field(default=None, max_length=1024)


class CodigoServicoUpdate(BaseModel):
    """Admin: atualiza um código de serviço."""

    descricao: str | None = Field(default=None, max_length=500)
    valor_centavos: int | None = Field(default=None, ge=0)
    categoria: str | None = Field(default=None, max_length=120)
    porte: str | None = Field(default=None, max_length=40)
    ativo: bool | None = None
    observacoes: str | None = Field(default=None, max_length=1024)


# ============================================================
# Lançamentos
# ============================================================


class LancamentoCreate(BaseModel):
    """Médico cria um lançamento. O beneficiario_id vem do token de sessão."""

    codigo: str = Field(
        min_length=1, max_length=40,
        description="Código do serviço (busca em codigos_servico).",
    )
    data_servico: date
    hospital_local: str | None = Field(default=None, max_length=255)
    paciente_iniciais: str | None = Field(default=None, max_length=10)
    observacoes: str | None = Field(default=None, max_length=1024)


class LancamentoOut(BaseModel):
    """Lançamento (visão do médico após criar / listar)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    data_servico: date
    codigo_snapshot: str
    descricao_snapshot: str
    valor_centavos: int
    hospital_local: str | None
    paciente_iniciais: str | None
    observacoes: str | None
    status: StatusLancamento
    created_at: datetime


class LancamentosListResponse(BaseModel):
    """Resposta de listagem de lançamentos do médico."""

    items: list[LancamentoOut]
    total: int
    total_centavos: int


# ============================================================
# Importação de planilha (admin)
# ============================================================


class ImportacaoCodigosResultado(BaseModel):
    """Resultado da importação da planilha de códigos."""

    criados: int
    atualizados: int
    inalterados: int
    erros: list[str]
    total_linhas: int


__all__ = [
    "CodigoServicoCreate",
    "CodigoServicoOut",
    "CodigoServicoUpdate",
    "CrmLoginRequest",
    "CrmLoginResponse",
    "ImportacaoCodigosResultado",
    "LancamentoCreate",
    "LancamentoOut",
    "LancamentosListResponse",
    "MedicoOut",
]
