"""Schemas das rotas administrativas: gestão de usuários e relatórios.

Tudo aqui é acessível apenas por usuários com `role=ADMIN` (Thiago e
diretoria). A área cobre:

- Cadastro/edição/desativação de operadores e aprovadores
- Reset de senha (recurso operacional, evita ticket de TI)
- Relatórios de erros por operador (treinamento e accountability)
- Relatórios de devolução do banco (visibilidade de motivo de retorno)

Os relatórios são pensados para **escala**: a empresa do Thiago processa
milhares de pagamentos por mês, então tudo aqui é paginado e suporta
filtros de período + cliente + operador.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


# ============================================================
# CRUD de usuários
# ============================================================


class UserAdminOut(BaseModel):
    """Usuário visto pela área admin (inclui campos sensíveis de gestão)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    nome: str
    role: UserRole
    ativo: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class CriarUsuarioRequest(BaseModel):
    """Payload pra criar um novo operador/aprovador/admin."""

    email: EmailStr
    nome: str = Field(min_length=2, max_length=255)
    role: UserRole
    senha: str = Field(min_length=8, max_length=128)


class AtualizarUsuarioRequest(BaseModel):
    """Edição parcial de usuário (PATCH). Todos os campos opcionais."""

    nome: str | None = Field(default=None, min_length=2, max_length=255)
    role: UserRole | None = None
    ativo: bool | None = None


class ResetSenhaRequest(BaseModel):
    """Reset de senha imposto pelo admin."""

    nova_senha: str = Field(min_length=8, max_length=128)


# ============================================================
# Relatório de erros por operador
# ============================================================


class ErrosPorOperador(BaseModel):
    """Linha do ranking de operadores por volume de erro."""

    operador_id: UUID | None = None
    operador_nome: str
    operador_email: str | None = None
    total_lotes: int
    total_pagamentos: int
    total_bloqueados: int
    total_corrigiveis: int
    taxa_erro_pct: float = Field(description="(bloqueados+corrigiveis)/total * 100")
    valor_bloqueado_centavos: int = Field(
        description="Quanto em R$ foi bloqueado — proxy do prejuízo evitado"
    )


class ErrosPorTipo(BaseModel):
    """Agregação por código de erro (ex: CPF_INVALIDO, VALOR_SUSPEITO)."""

    codigo: str
    descricao: str
    quantidade: int
    valor_centavos: int


class ErrosPorHospital(BaseModel):
    """Agregação por cliente/hospital."""

    cliente_id: UUID
    cliente_nome: str
    total_lotes: int
    total_pagamentos: int
    total_bloqueados: int
    taxa_erro_pct: float


class RelatorioErrosResponse(BaseModel):
    """Resposta completa do relatório de erros — feita pra renderizar
    direto numa página com KPIs grandes no topo e tabelas embaixo.
    """

    periodo_inicio: datetime
    periodo_fim: datetime

    # KPIs
    total_lotes_processados: int
    total_pagamentos: int
    total_bloqueados: int
    total_corrigiveis: int
    valor_total_centavos: int
    valor_bloqueado_centavos: int = Field(
        description="PREJUÍZO EVITADO — soma de valores que seriam pagos errados"
    )
    taxa_erro_pct: float

    # Detalhe
    por_operador: list[ErrosPorOperador]
    por_tipo_erro: list[ErrosPorTipo]
    por_hospital: list[ErrosPorHospital]


# ============================================================
# Relatório de devoluções do banco (.ret)
# ============================================================


class DevolucaoBanco(BaseModel):
    """Um pagamento devolvido pelo banco com motivo decodificado."""

    pagamento_id: UUID
    lote_id: UUID
    lote_nome: str
    cliente_nome: str
    linha_planilha: int
    nome_beneficiario: str
    cpf_mascarado: str
    valor_centavos: int
    retorno_codigo: str | None
    retorno_descricao: str | None
    motivo_conhecido: bool = Field(
        description="True se conseguimos traduzir o código do banco"
    )
    pago_at: datetime | None
    operador_nome: str | None = Field(
        default=None, description="Quem subiu a planilha originalmente"
    )


class DevolucoesPorMotivo(BaseModel):
    """Agregação por motivo de devolução."""

    codigo: str
    descricao: str
    quantidade: int
    valor_centavos: int


class RelatorioDevolucoesResponse(BaseModel):
    """Devoluções do banco em um período."""

    periodo_inicio: datetime
    periodo_fim: datetime

    total_devolucoes: int
    total_motivo_conhecido: int
    total_motivo_desconhecido: int
    valor_total_devolvido_centavos: int

    por_motivo: list[DevolucoesPorMotivo]
    devolucoes: list[DevolucaoBanco] = Field(description="Detalhe paginado")
