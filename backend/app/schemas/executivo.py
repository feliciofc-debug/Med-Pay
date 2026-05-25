"""Schemas Pydantic do Dashboard Executivo e Contratos.

Espelha os tipos do frontend (`frontend/src/types/index.ts`) pra manter
compatibilidade do mock antigo (demo.ts) com o backend real. Assim a UI
não precisa mudar — só passa a consumir dados de verdade.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# Contratos — configuração comercial
# ============================================================


class ConfiguracaoCobranca(BaseModel):
    mensalidade_centavos: int = Field(ge=0, default=0)
    taxa_por_pagamento_centavos: int = Field(ge=0, default=0)
    percentual_volume_bp: int = Field(ge=0, default=0)
    volume_medio_mensal_centavos: int = Field(ge=0, default=0)


class ConfiguracaoCusto(BaseModel):
    custo_fixo_mensal_centavos: int = Field(ge=0, default=0)
    custo_variavel_pct: int = Field(ge=0, le=100, default=0)


class ContratoOut(BaseModel):
    """Shape do contrato exposto pra UI (compatível com `ContratoConfig`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    cliente_nome: str
    cliente_cnpj: str | None = None
    cobranca: ConfiguracaoCobranca
    custo: ConfiguracaoCusto
    meta_mensal_centavos: int
    vigencia_inicio: date
    vencimento: date | None  # alias do vigencia_fim, pra match com mock
    ativo: bool
    observacoes: str | None = None


class SalvarContratoRequest(BaseModel):
    """Payload pra criar ou atualizar contrato (PUT idempotente)."""

    cobranca: ConfiguracaoCobranca
    custo: ConfiguracaoCusto
    meta_mensal_centavos: int = Field(ge=0, default=0)
    vencimento: date | None = None
    observacoes: str | None = None


# ============================================================
# Dashboard Executivo
# ============================================================


SaudeContrato = Literal["saudavel", "atencao", "critico"]


class ContratoFinanceiro(BaseModel):
    """Linha do "Receita por contrato" no Executivo."""

    cliente_id: UUID
    cliente_nome: str
    receita_mes_centavos: int
    custo_mes_centavos: int
    margem_pct: float
    margem_delta_pp: float  # pontos percentuais vs mês anterior
    saude: SaudeContrato
    lotes_mes: int
    pagamentos_mes: int
    ultima_atividade: datetime | None


class ProjecaoMensal(BaseModel):
    mes: str  # ex.: "Jun/26"
    receita_centavos: int
    meta_centavos: int
    realizado: bool


class KPIOperacional(BaseModel):
    lotes_processados: int
    lotes_aguardando: int
    tempo_medio_processamento_min: float
    taxa_erro_pct: float
    pagamentos_mes: int
    conciliados_pct: float


AlertaSeveridade = Literal["critico", "atencao", "info"]


class AlertaExecutivo(BaseModel):
    id: str
    severidade: AlertaSeveridade
    titulo: str
    descricao: str
    cliente_nome: str | None = None
    acao_sugerida: str | None = None
    created_at: datetime


class RenovacaoProxima(BaseModel):
    cliente_id: UUID
    cliente_nome: str
    vencimento: date
    dias_restantes: int
    margem_atual_pct: float
    recomendacao: Literal["manter", "reajustar", "renegociar_urgente"]
    reajuste_sugerido_pct: float | None = None


class KPIHero(BaseModel):
    lucro_liquido_centavos: int
    receita_total_centavos: int
    custo_total_centavos: int
    margem_media_pct: float
    delta_lucro_pct: float  # vs mês anterior
    meta_total_centavos: int
    meta_atingida_pct: float


class DashboardExecutivo(BaseModel):
    """Resposta completa do Dashboard Executivo."""

    gerado_em: datetime
    mes_referencia: str  # ex.: "Junho/2026"
    kpi_hero: KPIHero
    contratos: list[ContratoFinanceiro]
    projecao_12m: list[ProjecaoMensal]
    kpi_operacional: KPIOperacional
    alertas: list[AlertaExecutivo]
    renovacoes_proximas: list[RenovacaoProxima]
    receita_prevista_centavos: int = 0  # vinda das fichas em revisão
    margem_prevista_centavos: int = 0


# ============================================================
# Painel do Coordenador
# ============================================================


class FichaCoordenadorResumo(BaseModel):
    id: UUID
    cliente_nome: str
    nome_arquivo: str
    competencia: str | None  # extraído dos metadados (ex: "Junho/2026")
    status: str
    total_linhas: int
    valor_total_centavos: int
    created_at: datetime
    duplicada_de_id: UUID | None = None  # se for duplicata, aponta pra original
    motivo_duplicidade: str | None = None


class BancoHorasMedico(BaseModel):
    """Linha do extrato 'banco de horas' do coordenador."""

    cpf_mascarado: str
    nome: str
    qtd_fichas: int
    horas_total: int
    valor_total_centavos: int
    competencias: list[str]  # meses em que apareceu (ajuda a ver duplicata)
    ultima_ficha_id: UUID
    ultima_ficha_em: datetime


class PainelCoordenadorOut(BaseModel):
    """Visão completa pro coordenador no /app/coordenador."""

    gerado_em: datetime
    fichas_recentes: list[FichaCoordenadorResumo]
    banco_horas: list[BancoHorasMedico]
    qtd_fichas_total: int
    qtd_fichas_mes: int
    qtd_lotes_gerados: int
    valor_total_mes_centavos: int
    duplicatas_potenciais: int  # nº de fichas com sinal de duplicata
