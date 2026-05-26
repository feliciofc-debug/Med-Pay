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

from app.models.empresa_config import BancoEmissor, TipoInscricao
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


# ============================================================
# Empresa pagadora (dados da Unicred do Thiago)
# ============================================================
#
# Singleton: existe no máximo um registro ativo no sistema. Esses dados
# entram no Header do CNAB 240 — qualquer pagamento gerado pelo MedPag
# carrega a identidade dessa empresa. Mudar isso DEPOIS de um arquivo
# gerado pode causar inconsistência de conciliação no banco, então a
# edição é protegida por ADMIN e logada em auditoria.


class EmpresaPagadoraOut(BaseModel):
    """Dados da empresa pagadora, conta mascarada para exibição."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    razao_social: str
    nome_fantasia: str | None
    tipo_inscricao: TipoInscricao
    cnpj_cpf: str

    banco_emissor: BancoEmissor
    banco_codigo: str
    agencia: str
    agencia_dv: str | None
    conta_mascarada: str
    conta_dv: str
    codigo_convenio: str

    endereco_logradouro: str
    endereco_numero: str
    endereco_complemento: str | None
    endereco_cidade: str
    endereco_cep: str
    endereco_uf: str

    proximo_numero_sequencial: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


class EmpresaPagadoraRequest(BaseModel):
    """Payload pra criar ou substituir os dados da empresa pagadora.

    PUT idempotente: se já existir registro ativo, substitui; senão cria.
    Os campos são todos obrigatórios — não dá pra fazer PATCH parcial
    porque o CNAB exige todos preenchidos pra ser válido.
    """

    razao_social: str = Field(min_length=2, max_length=255)
    nome_fantasia: str | None = Field(default=None, max_length=255)
    tipo_inscricao: TipoInscricao = TipoInscricao.CNPJ
    cnpj_cpf: str = Field(
        min_length=11,
        max_length=18,
        description="CPF (11) ou CNPJ (14) sem formatação — pode vir com pontos",
    )

    banco_emissor: BancoEmissor = Field(
        default=BancoEmissor.UNICRED,
        description="Qual adapter de CNAB usar: UNICRED, ITAU ou BRADESCO",
    )
    banco_codigo: str = Field(default="136", min_length=3, max_length=3)
    agencia: str = Field(min_length=1, max_length=5)
    agencia_dv: str | None = Field(default=None, max_length=1)
    conta: str = Field(
        min_length=1, max_length=20, description="Conta sem dígito (DV vai separado)"
    )
    conta_dv: str = Field(min_length=1, max_length=1)
    codigo_convenio: str = Field(min_length=1, max_length=20)

    endereco_logradouro: str = Field(min_length=2, max_length=30)
    endereco_numero: str = Field(min_length=1, max_length=5)
    endereco_complemento: str | None = Field(default=None, max_length=15)
    endereco_cidade: str = Field(min_length=2, max_length=20)
    endereco_cep: str = Field(min_length=8, max_length=9)
    endereco_uf: str = Field(min_length=2, max_length=2)

    proximo_numero_sequencial: int = Field(default=1, ge=1)
