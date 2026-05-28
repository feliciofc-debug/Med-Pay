"""Métricas executivas pra o Painel Super Admin.

Calcula a saúde comercial da MedPag inteira:
    - MRR / ARR (receita recorrente baseada nos planos dos clientes ativos)
    - Distribuição por status de assinatura
    - Lista de clientes com health score (verde/amarelo/vermelho) baseado em:
        * Último login do usuário admin do cliente
        * Uso recente (lotes processados nos últimos 30 dias)
        * Status de assinatura
    - Funil de novos clientes no mês

Premissas de receita:
    - Clientes em ATIVO ou INADIMPLENTE contam pro MRR bruto.
      Trial = R$ 0 (ainda não convertido).
      Suspenso/Cancelado = R$ 0.
    - Plano Enterprise (preco_mensal_centavos=0 = sob demanda)
      não contribui pra MRR automático — entra como zero.
      Quando integrarmos cobrança, salvamos override por contrato.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cliente import Cliente
from app.models.lote import Lote
from app.models.plano import Plano, StatusAssinatura
from app.models.user import User


# ============================================================
# Resultado
# ============================================================


@dataclass(slots=True)
class MetricasSaaS:
    """Snapshot das métricas comerciais agora."""

    # Receita
    mrr_centavos: int                # soma do preço dos planos ativos
    arr_centavos: int                # mrr * 12
    arpu_centavos: int               # mrr / clientes pagantes
    receita_potencial_trial: int     # mrr "se" os trials converterem

    # Contagens
    clientes_total: int
    clientes_pagantes: int           # ATIVO + INADIMPLENTE
    clientes_trial: int
    clientes_suspensos: int
    clientes_cancelados: int

    # Funil
    novos_30d: int
    novos_no_mes: int
    cancelados_no_mes: int

    # Trial vencendo
    trials_vencendo_7d: int

    # Distribuição por plano
    distribuicao_plano: list[dict[str, Any]]  # [{slug, nome, count, mrr}]


@dataclass(slots=True)
class ClienteOverview:
    """Visão consolidada por cliente pra a tabela do super admin."""

    id: str
    nome: str
    cnpj: str | None
    plano_nome: str | None
    status_assinatura: str
    trial_termina_em: datetime | None
    mrr_centavos: int
    ultimo_login: datetime | None
    lotes_30d: int
    health_score: str   # "VERDE" | "AMARELO" | "VERMELHO" | "CINZA"
    sinais: list[str]   # explicações textuais ("sem login há 14 dias", etc)


# ============================================================
# Cálculo
# ============================================================


def _agora_utc() -> datetime:
    return datetime.now(UTC)


def _conta_mrr(cliente: Cliente) -> int:
    """Quanto este cliente contribui pro MRR agora.

    Trial → 0
    Cancelado/Suspenso → 0
    Ativo/Inadimplente → preço do plano (Enterprise=0 fica como 0 mesmo)
    """
    if cliente.status_assinatura in (
        StatusAssinatura.TRIAL,
        StatusAssinatura.SUSPENSO,
        StatusAssinatura.CANCELADO,
    ):
        return 0
    if cliente.plano is None:
        return 0
    return int(cliente.plano.preco_mensal_centavos)


async def calcular_metricas(db: AsyncSession) -> MetricasSaaS:
    """Calcula tudo de uma vez (uma query principal + 2 auxiliares)."""

    # Query principal: todos os clientes com plano em uma ida só
    result = await db.execute(
        select(Cliente)
        .where(Cliente.deleted_at.is_(None))
        .options(selectinload(Cliente.plano))
    )
    clientes: Sequence[Cliente] = result.scalars().all()

    agora = _agora_utc()
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sete_dias_atras = agora - timedelta(days=7)
    trinta_dias_atras = agora - timedelta(days=30)

    mrr = 0
    trial_potencial = 0
    pagantes = 0
    trial = 0
    suspensos = 0
    cancelados = 0
    novos_30 = 0
    novos_mes = 0
    trial_vencendo = 0

    # Distribuição por plano
    plano_buckets: dict[str, dict[str, Any]] = {}

    for c in clientes:
        if c.created_at >= trinta_dias_atras:
            novos_30 += 1
        if c.created_at >= inicio_mes:
            novos_mes += 1

        if c.status_assinatura == StatusAssinatura.TRIAL:
            trial += 1
            if c.plano:
                trial_potencial += c.plano.preco_mensal_centavos
            if (
                c.trial_termina_em
                and sete_dias_atras < c.trial_termina_em < agora + timedelta(days=7)
            ):
                trial_vencendo += 1
        elif c.status_assinatura in (StatusAssinatura.ATIVO, StatusAssinatura.INADIMPLENTE):
            pagantes += 1
            mrr += _conta_mrr(c)
        elif c.status_assinatura == StatusAssinatura.SUSPENSO:
            suspensos += 1
        elif c.status_assinatura == StatusAssinatura.CANCELADO:
            cancelados += 1

        # Distribuição
        slug = c.plano.slug if c.plano else "sem_plano"
        bucket = plano_buckets.setdefault(
            slug,
            {
                "slug": slug,
                "nome": c.plano.nome if c.plano else "Sem plano",
                "count": 0,
                "mrr_centavos": 0,
            },
        )
        bucket["count"] += 1
        bucket["mrr_centavos"] += _conta_mrr(c)

    # Cancelados no mês — via filtro de updated_at (proxy razoável enquanto não
    # temos um campo `cancelado_em`. Quando tivermos, troca aqui).
    cancelados_mes_q = await db.execute(
        select(func.count(Cliente.id))
        .where(
            Cliente.deleted_at.is_(None),
            Cliente.status_assinatura == StatusAssinatura.CANCELADO,
            Cliente.updated_at >= inicio_mes,
        )
    )
    cancelados_no_mes = int(cancelados_mes_q.scalar() or 0)

    arr = mrr * 12
    arpu = mrr // pagantes if pagantes > 0 else 0

    distribuicao = sorted(
        plano_buckets.values(), key=lambda b: -b["mrr_centavos"]
    )

    return MetricasSaaS(
        mrr_centavos=mrr,
        arr_centavos=arr,
        arpu_centavos=arpu,
        receita_potencial_trial=trial_potencial,
        clientes_total=len(clientes),
        clientes_pagantes=pagantes,
        clientes_trial=trial,
        clientes_suspensos=suspensos,
        clientes_cancelados=cancelados,
        novos_30d=novos_30,
        novos_no_mes=novos_mes,
        cancelados_no_mes=cancelados_no_mes,
        trials_vencendo_7d=trial_vencendo,
        distribuicao_plano=distribuicao,
    )


# ============================================================
# Lista detalhada com health score
# ============================================================


def _health_score(
    *,
    status: StatusAssinatura,
    ultimo_login: datetime | None,
    lotes_30d: int,
    trial_termina_em: datetime | None,
    agora: datetime,
) -> tuple[str, list[str]]:
    """Calcula cor de saúde + lista de sinais que justificam."""
    sinais: list[str] = []

    if status == StatusAssinatura.CANCELADO:
        return "CINZA", ["assinatura cancelada"]
    if status == StatusAssinatura.SUSPENSO:
        return "VERMELHO", ["assinatura suspensa"]

    cor = "VERDE"

    if status == StatusAssinatura.INADIMPLENTE:
        sinais.append("pagamento em atraso")
        cor = "AMARELO"

    if status == StatusAssinatura.TRIAL:
        if trial_termina_em:
            dias = (trial_termina_em - agora).days
            if dias < 0:
                sinais.append("trial expirado")
                cor = "VERMELHO"
            elif dias <= 3:
                sinais.append(f"trial vence em {dias} dias")
                if cor == "VERDE":
                    cor = "AMARELO"

    if ultimo_login is None:
        sinais.append("nunca logou")
        cor = "VERMELHO" if cor != "VERDE" else "AMARELO"
    else:
        dias_login = (agora - ultimo_login).days
        if dias_login > 30:
            sinais.append(f"sem login há {dias_login}d")
            cor = "VERMELHO"
        elif dias_login > 14:
            sinais.append(f"sem login há {dias_login}d")
            if cor == "VERDE":
                cor = "AMARELO"

    if lotes_30d == 0 and status != StatusAssinatura.TRIAL:
        sinais.append("sem lotes processados em 30d")
        if cor == "VERDE":
            cor = "AMARELO"

    if not sinais:
        sinais.append("uso saudável")

    return cor, sinais


async def listar_clientes_overview(
    db: AsyncSession, *, limite: int = 200
) -> list[ClienteOverview]:
    """Tabela de clientes com plano, status, uso e health score.

    NOTA: hoje a plataforma é BPO, então "último login" do cliente é
    aproximado pelo último login de QUALQUER usuário (todos os usuários
    são da MedPag). Quando migrarmos pra multi-tenant com User.cliente_id,
    refinamos.
    """
    agora = _agora_utc()
    trinta_dias_atras = agora - timedelta(days=30)

    # Clientes + plano
    result = await db.execute(
        select(Cliente)
        .where(Cliente.deleted_at.is_(None))
        .options(selectinload(Cliente.plano))
        .order_by(Cliente.nome)
        .limit(limite)
    )
    clientes: Sequence[Cliente] = result.scalars().all()
    if not clientes:
        return []

    cliente_ids = [c.id for c in clientes]

    # Lotes nos últimos 30 dias por cliente
    lotes_q = await db.execute(
        select(Lote.cliente_id, func.count(Lote.id))
        .where(
            Lote.cliente_id.in_(cliente_ids),
            Lote.created_at >= trinta_dias_atras,
        )
        .group_by(Lote.cliente_id)
    )
    lotes_por_cliente: dict[Any, int] = {
        row[0]: int(row[1]) for row in lotes_q.all()
    }

    # "Último login" — pegamos o último login global; é aproximação até multi-tenant
    last_login_q = await db.execute(
        select(func.max(User.last_login_at)).where(User.ativo.is_(True))
    )
    ultimo_login_global = last_login_q.scalar_one_or_none()

    overview: list[ClienteOverview] = []
    for c in clientes:
        lotes_30 = lotes_por_cliente.get(c.id, 0)
        cor, sinais = _health_score(
            status=c.status_assinatura,
            ultimo_login=ultimo_login_global,
            lotes_30d=lotes_30,
            trial_termina_em=c.trial_termina_em,
            agora=agora,
        )
        overview.append(
            ClienteOverview(
                id=str(c.id),
                nome=c.nome,
                cnpj=c.cnpj,
                plano_nome=c.plano.nome if c.plano else None,
                status_assinatura=c.status_assinatura.value,
                trial_termina_em=c.trial_termina_em,
                mrr_centavos=_conta_mrr(c),
                ultimo_login=ultimo_login_global,
                lotes_30d=lotes_30,
                health_score=cor,
                sinais=sinais,
            )
        )
    return overview


__all__ = [
    "ClienteOverview",
    "MetricasSaaS",
    "calcular_metricas",
    "listar_clientes_overview",
]
