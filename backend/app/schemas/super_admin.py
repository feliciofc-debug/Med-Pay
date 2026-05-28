"""Schemas Pydantic do Painel Super Admin."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MetricasSaaSOut(BaseModel):
    mrr_centavos: int
    arr_centavos: int
    arpu_centavos: int
    receita_potencial_trial: int

    clientes_total: int
    clientes_pagantes: int
    clientes_trial: int
    clientes_suspensos: int
    clientes_cancelados: int

    novos_30d: int
    novos_no_mes: int
    cancelados_no_mes: int

    trials_vencendo_7d: int

    distribuicao_plano: list[dict[str, Any]]


class ClienteOverviewOut(BaseModel):
    id: str
    nome: str
    cnpj: str | None
    plano_nome: str | None
    status_assinatura: str
    trial_termina_em: datetime | None
    mrr_centavos: int
    ultimo_login: datetime | None
    lotes_30d: int
    health_score: str
    sinais: list[str]


__all__ = ["ClienteOverviewOut", "MetricasSaaSOut"]
