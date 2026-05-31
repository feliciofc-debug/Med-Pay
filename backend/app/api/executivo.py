"""Rotas do Dashboard Executivo, Contratos e Painel do Coordenador.

Reúne 3 superfícies relacionadas:

- `/api/contratos`: CRUD do `ContratoHospital` (substitui o mock antigo
  do front).

- `/api/dashboard/executivo`: agregação em tempo real de receita, custo
  e margem por hospital, baseada em lotes + pagamentos + fichas reais
  (não mais o `demo.ts`).

- `/api/coordenador/meu-painel`: visão restrita pro funcionário interno
  que sobe fichas — só vê o que ele subiu, com extrato de banco de
  horas pra evitar duplicação da mesma operação.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import (
    get_current_user,
    get_db,
    get_tenant_id,
    require_admin,
    require_visao_executiva,
)
from app.core.exceptions import (
    PermissaoNegadaError,
    ValidacaoError,
)
from app.models.cliente import Cliente
from app.models.contrato_hospital import ContratoHospital, ModoCobranca
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote, StatusLote
from app.models.scp import ApuracaoSCP
from app.models.user import User, UserRole
from app.schemas.executivo import (
    AlertaExecutivo,
    BancoHorasMedico,
    ClienteSemContratoOut,
    ContratoFinanceiro,
    ContratoOut,
    DashboardExecutivo,
    FichaCoordenadorResumo,
    KPIHero,
    KPIOperacional,
    PainelCoordenadorOut,
    ProjecaoMensal,
    RenovacaoProxima,
    ResumoOperacaoMes,
    ResumoPipelineHospital,
    SalvarContratoRequest,
)

log = structlog.get_logger()

router = APIRouter()


# ============================================================
# Helpers — agregação financeira
# ============================================================


def _inicio_mes(d: date) -> date:
    return d.replace(day=1)


def _proximo_mes(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _calcular_receita(
    cobranca_mensalidade: int,
    cobranca_taxa_pgto: int,
    cobranca_pct_volume_bp: int,
    qtd_pagamentos: int,
    volume_centavos: int,
) -> int:
    """Receita do contrato no período (em centavos).

    receita = mensalidade
            + (qtd_pagamentos × taxa_por_pagamento)
            + (volume × pct_volume_bp / 10_000)
    """
    receita = cobranca_mensalidade
    receita += qtd_pagamentos * cobranca_taxa_pgto
    receita += round(volume_centavos * cobranca_pct_volume_bp / 10_000)
    return receita


def _calcular_custo(
    custo_fixo: int, custo_variavel_pct: int, receita_centavos: int
) -> int:
    return custo_fixo + round(receita_centavos * custo_variavel_pct / 100)


def _saude_contrato(margem_pct: float, delta_pp: float) -> str:
    if margem_pct < 40:
        return "critico"
    if margem_pct < 55 or delta_pp <= -5:
        return "atencao"
    return "saudavel"


# ============================================================
# Contratos — CRUD
# ============================================================


def _serializar_contrato(c: ContratoHospital) -> ContratoOut:
    return ContratoOut(
        id=c.id,
        cliente_id=c.cliente_id,
        cliente_nome=c.cliente.nome,
        cliente_cnpj=c.cliente.cnpj,
        cobranca={
            "mensalidade_centavos": c.mensalidade_centavos,
            "taxa_por_pagamento_centavos": c.taxa_por_pagamento_centavos,
            "percentual_volume_bp": c.percentual_volume_bp,
            "volume_medio_mensal_centavos": c.volume_medio_mensal_centavos,
        },
        custo={
            "custo_fixo_mensal_centavos": c.custo_fixo_mensal_centavos,
            "custo_variavel_pct": c.custo_variavel_pct,
        },
        meta_mensal_centavos=c.meta_mensal_centavos,
        vigencia_inicio=c.vigencia_inicio,
        vencimento=c.vigencia_fim,
        ativo=c.ativo,
        modo_cobranca=c.modo_cobranca.value if c.modo_cobranca else "PERCENTUAL_REPASSE",
        observacoes=c.observacoes,
    )


@router.get("/contratos", response_model=list[ContratoOut])
async def listar_contratos(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_visao_executiva),
) -> list[ContratoOut]:
    """Lista os contratos vigentes (1 por cliente)."""
    result = await db.execute(
        select(ContratoHospital)
        .where(ContratoHospital.ativo.is_(True))
        .options(selectinload(ContratoHospital.cliente))
        .order_by(ContratoHospital.created_at.desc())
    )
    return [_serializar_contrato(c) for c in result.scalars().all()]


@router.put("/contratos/{cliente_id}", response_model=ContratoOut)
async def salvar_contrato(
    cliente_id: UUID,
    payload: SalvarContratoRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ContratoOut:
    """Cria ou atualiza o contrato do hospital (PUT idempotente).

    Se já existe contrato ativo, atualiza os campos. Senão cria.
    Mantemos só 1 ativo por cliente (constraint do índice parcial).
    """
    cliente_q = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_q.scalar_one_or_none()
    if cliente is None:
        raise ValidacaoError(f"Cliente {cliente_id} não encontrado")

    contrato_q = await db.execute(
        select(ContratoHospital).where(
            ContratoHospital.cliente_id == cliente_id,
            ContratoHospital.ativo.is_(True),
        )
    )
    contrato = contrato_q.scalar_one_or_none()

    if contrato is None:
        contrato = ContratoHospital(
            cliente_id=cliente_id,
            mensalidade_centavos=payload.cobranca.mensalidade_centavos,
            taxa_por_pagamento_centavos=payload.cobranca.taxa_por_pagamento_centavos,
            percentual_volume_bp=payload.cobranca.percentual_volume_bp,
            volume_medio_mensal_centavos=payload.cobranca.volume_medio_mensal_centavos,
            custo_fixo_mensal_centavos=payload.custo.custo_fixo_mensal_centavos,
            custo_variavel_pct=payload.custo.custo_variavel_pct,
            meta_mensal_centavos=payload.meta_mensal_centavos,
            vigencia_fim=payload.vencimento,
            modo_cobranca=ModoCobranca(payload.modo_cobranca),
            observacoes=payload.observacoes,
            ativo=True,
        )
        db.add(contrato)
    else:
        contrato.mensalidade_centavos = payload.cobranca.mensalidade_centavos
        contrato.taxa_por_pagamento_centavos = (
            payload.cobranca.taxa_por_pagamento_centavos
        )
        contrato.percentual_volume_bp = payload.cobranca.percentual_volume_bp
        contrato.volume_medio_mensal_centavos = (
            payload.cobranca.volume_medio_mensal_centavos
        )
        contrato.custo_fixo_mensal_centavos = (
            payload.custo.custo_fixo_mensal_centavos
        )
        contrato.custo_variavel_pct = payload.custo.custo_variavel_pct
        contrato.meta_mensal_centavos = payload.meta_mensal_centavos
        contrato.vigencia_fim = payload.vencimento
        contrato.modo_cobranca = ModoCobranca(payload.modo_cobranca)
        contrato.observacoes = payload.observacoes

    await db.flush()
    await db.refresh(contrato, attribute_names=["cliente"])

    log.info(
        "executivo.contrato_salvo",
        admin=admin.email,
        cliente=cliente.nome,
        cliente_id=str(cliente_id),
    )
    return _serializar_contrato(contrato)


@router.get(
    "/contratos/clientes-sem-contrato",
    response_model=list[ClienteSemContratoOut],
)
async def listar_clientes_sem_contrato(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_visao_executiva),
) -> list[ClienteSemContratoOut]:
    """Clientes que têm atividade no sistema mas não têm contrato ativo.

    Ajuda o admin a identificar hospitais "esquecidos" — operando sem
    contrato comercial cadastrado e portanto sem aparecer em receita,
    margem e renovação no Executivo.

    Inclui também clientes sem atividade alguma (qtd_lotes_30d=0), pra
    o fluxo "criar contrato pra hospital novo".
    """
    inicio_30d = datetime.now(tz=UTC) - timedelta(days=30)

    # Subquery: clientes com contrato ativo
    contrato_subq = (
        select(ContratoHospital.cliente_id)
        .where(ContratoHospital.ativo.is_(True))
        .subquery()
    )

    # Clientes ativos sem contrato + agregados de lotes nos últimos 30d
    lotes_count = func.count(Lote.id).label("lotes_30d")
    lotes_valor = func.coalesce(func.sum(Lote.valor_total_centavos), 0).label(
        "valor_30d"
    )
    ultima = func.max(Lote.created_at).label("ultima")

    result = await db.execute(
        select(
            Cliente.id,
            Cliente.nome,
            Cliente.cnpj,
            lotes_count,
            lotes_valor,
            ultima,
        )
        .outerjoin(
            Lote,
            and_(
                Lote.cliente_id == Cliente.id,
                Lote.created_at >= inicio_30d,
            ),
        )
        .where(
            Cliente.deleted_at.is_(None),
            Cliente.ativo.is_(True),
            Cliente.id.not_in(select(contrato_subq.c.cliente_id)),
        )
        .group_by(Cliente.id, Cliente.nome, Cliente.cnpj)
        .order_by(lotes_count.desc(), Cliente.nome)
    )
    return [
        ClienteSemContratoOut(
            cliente_id=row.id,
            nome=row.nome,
            cnpj=row.cnpj,
            qtd_lotes_30d=int(row.lotes_30d or 0),
            valor_processado_30d_centavos=int(row.valor_30d or 0),
            ultima_atividade=row.ultima,
        )
        for row in result.all()
    ]


# ============================================================
# Dashboard Executivo
# ============================================================


@router.get("/dashboard/executivo", response_model=DashboardExecutivo)
async def dashboard_executivo(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> DashboardExecutivo:
    """Agrega receita, custo e margem usando dados REAIS, escopado por tenant.

    - MedPag interno (tenant_id None): vê todos os tenants (visão BPO).
    - Tenant (hospital/repasse): vê só os próprios dados.

    Modelo hospital/BPO (tem contrato):
        receita_mes = mensalidade + qtd_pgto×taxa + volume×pct_bp
        custo_mes   = custo_fixo + receita×custo_var_pct

    Modelo repasse/SCP (tem apuração SCP no mês): o KPI Hero passa a refletir
    a apuração da SCP — receita bruta, custos e resultado (margem) reais do
    período — em vez de ficar zerado por não ter contrato de hospital.
    """
    hoje = datetime.now(tz=UTC).date()
    inicio = _inicio_mes(hoje)
    fim = _proximo_mes(inicio)
    mes_anterior_inicio = _inicio_mes(inicio - timedelta(days=1))

    # 1) Carrega contratos ativos com cliente (escopado por tenant)
    contratos_stmt = (
        select(ContratoHospital)
        .where(ContratoHospital.ativo.is_(True))
        .options(selectinload(ContratoHospital.cliente))
    )
    if tenant_id is not None:
        contratos_stmt = contratos_stmt.where(
            ContratoHospital.cliente_id == tenant_id
        )
    contratos_q = await db.execute(contratos_stmt)
    contratos = list(contratos_q.scalars().all())

    # 2) Agrega lotes do mês corrente (status que conta como volume)
    status_volume = (
        StatusLote.APROVADO,
        StatusLote.ENVIADO_BANCO,
        StatusLote.PROCESSANDO,
        StatusLote.AGUARDANDO_REVISAO,
        StatusLote.CONCILIADO,
    )

    def _query_volume_por_cliente(inicio_periodo: date, fim_periodo: date):  # type: ignore[no-untyped-def]
        stmt = (
            select(
                Lote.cliente_id.label("cid"),
                func.count(Lote.id).label("qtd_lotes"),
                func.coalesce(func.sum(Lote.total_pagamentos), 0).label(
                    "qtd_pagamentos"
                ),
                func.coalesce(func.sum(Lote.valor_total_centavos), 0).label(
                    "volume"
                ),
                func.max(Lote.created_at).label("ultima_atividade"),
            )
            .where(
                and_(
                    Lote.created_at >= datetime.combine(inicio_periodo, datetime.min.time(), UTC),
                    Lote.created_at < datetime.combine(fim_periodo, datetime.min.time(), UTC),
                    Lote.status.in_(status_volume),
                )
            )
            .group_by(Lote.cliente_id)
        )
        if tenant_id is not None:
            stmt = stmt.where(Lote.cliente_id == tenant_id)
        return stmt

    mes_q = await db.execute(_query_volume_por_cliente(inicio, fim))
    mes_data: dict[UUID, dict[str, Any]] = {
        row.cid: {
            "qtd_lotes": row.qtd_lotes,
            "qtd_pagamentos": int(row.qtd_pagamentos),
            "volume": int(row.volume),
            "ultima": row.ultima_atividade,
        }
        for row in mes_q
    }

    mes_anterior_q = await db.execute(
        _query_volume_por_cliente(mes_anterior_inicio, inicio)
    )
    mes_anterior_data: dict[UUID, dict[str, Any]] = {
        row.cid: {
            "qtd_pagamentos": int(row.qtd_pagamentos),
            "volume": int(row.volume),
        }
        for row in mes_anterior_q
    }

    # 3) Constrói as linhas do Executivo
    linhas: list[ContratoFinanceiro] = []
    receita_total = 0
    custo_total = 0
    meta_total = 0

    for c in contratos:
        cid = c.cliente_id
        mes = mes_data.get(cid, {"qtd_lotes": 0, "qtd_pagamentos": 0, "volume": 0, "ultima": None})
        ant = mes_anterior_data.get(cid, {"qtd_pagamentos": 0, "volume": 0})

        # Volume usado pra cobrança: real do mês quando há, senão estimado
        volume_mes = mes["volume"] or c.volume_medio_mensal_centavos

        receita_mes = _calcular_receita(
            c.mensalidade_centavos,
            c.taxa_por_pagamento_centavos,
            c.percentual_volume_bp,
            mes["qtd_pagamentos"],
            volume_mes,
        )
        custo_mes = _calcular_custo(
            c.custo_fixo_mensal_centavos, c.custo_variavel_pct, receita_mes
        )
        margem_pct = (
            ((receita_mes - custo_mes) / receita_mes) * 100 if receita_mes > 0 else 0.0
        )

        # Mês anterior pra delta
        volume_ant = ant["volume"] or c.volume_medio_mensal_centavos
        receita_ant = _calcular_receita(
            c.mensalidade_centavos,
            c.taxa_por_pagamento_centavos,
            c.percentual_volume_bp,
            ant["qtd_pagamentos"],
            volume_ant,
        )
        custo_ant = _calcular_custo(
            c.custo_fixo_mensal_centavos, c.custo_variavel_pct, receita_ant
        )
        margem_ant_pct = (
            ((receita_ant - custo_ant) / receita_ant) * 100 if receita_ant > 0 else 0.0
        )
        delta_pp = round(margem_pct - margem_ant_pct, 2)

        linhas.append(
            ContratoFinanceiro(
                cliente_id=cid,
                cliente_nome=c.cliente.nome,
                receita_mes_centavos=receita_mes,
                custo_mes_centavos=custo_mes,
                margem_pct=round(margem_pct, 2),
                margem_delta_pp=delta_pp,
                saude=_saude_contrato(margem_pct, delta_pp),  # type: ignore[arg-type]
                lotes_mes=mes["qtd_lotes"],
                pagamentos_mes=mes["qtd_pagamentos"],
                ultima_atividade=mes["ultima"],
            )
        )

        receita_total += receita_mes
        custo_total += custo_mes
        meta_total += c.meta_mensal_centavos

    # Ordena por receita decrescente (cliente que rende mais aparece primeiro)
    linhas.sort(key=lambda x: x.receita_mes_centavos, reverse=True)

    # 4) KPI Hero
    lucro = receita_total - custo_total
    margem_media_pct = (lucro / receita_total) * 100 if receita_total > 0 else 0.0
    meta_atingida_pct = (receita_total / meta_total) * 100 if meta_total > 0 else 0.0
    kpi_hero = KPIHero(
        lucro_liquido_centavos=lucro,
        receita_total_centavos=receita_total,
        custo_total_centavos=custo_total,
        margem_media_pct=round(margem_media_pct, 2),
        delta_lucro_pct=0.0,  # melhoria futura: comparar com mês anterior
        meta_total_centavos=meta_total,
        meta_atingida_pct=round(meta_atingida_pct, 2),
    )

    # 5) Projeção 12 meses (simples: 3 anteriores reais + 9 lineares com meta)
    projecao = _montar_projecao_12m(
        receita_atual=receita_total, meta=meta_total, hoje=hoje
    )

    # 6) KPIs operacionais (inteiro mês)
    kpi_op = await _kpi_operacional(db, inicio, fim, tenant_id)

    # 7) Receita prevista de fichas em pipeline
    receita_prevista, margem_prevista = await _pipeline_fichas(
        db, inicio, fim, tenant_id
    )

    # 7b) Resumo "programação vs realizado" — sempre populado, mesmo sem contratos
    operacao_mes, pipeline_hospitais = await _pipeline_completo(
        db, inicio, fim, contratos, tenant_id
    )

    # 4b) Repasse/SCP: se o tenant tem apuração da SCP no mês, o KPI Hero passa
    # a refletir a apuração (receita bruta, custos, resultado) em vez de zero.
    if tenant_id is not None:
        kpi_hero = await _kpi_hero_scp(db, tenant_id, inicio, fallback=kpi_hero)

    # 8) Alertas (margem crítica + renovações vencendo)
    alertas: list[AlertaExecutivo] = []
    renovacoes: list[RenovacaoProxima] = []

    for linha in linhas:
        if linha.saude == "critico":
            alertas.append(
                AlertaExecutivo(
                    id=f"margem-{linha.cliente_id}",
                    severidade="critico",
                    titulo=f"Margem crítica em {linha.cliente_nome}",
                    descricao=(
                        f"Margem do mês está em {linha.margem_pct:.1f}%. "
                        f"Avalie reajuste contratual."
                    ),
                    cliente_nome=linha.cliente_nome,
                    acao_sugerida="Renegociar contrato",
                    created_at=datetime.now(UTC),
                )
            )
        elif linha.saude == "atencao":
            alertas.append(
                AlertaExecutivo(
                    id=f"queda-{linha.cliente_id}",
                    severidade="atencao",
                    titulo=f"Queda de margem em {linha.cliente_nome}",
                    descricao=(
                        f"Margem caiu {linha.margem_delta_pp:+.1f}pp vs mês anterior."
                    ),
                    cliente_nome=linha.cliente_nome,
                    acao_sugerida="Revisar custos do contrato",
                    created_at=datetime.now(UTC),
                )
            )

    for c in contratos:
        if c.vigencia_fim is None:
            continue
        dias = (c.vigencia_fim - hoje).days
        if 0 <= dias <= 60:
            linha_correspondente = next(
                (l for l in linhas if l.cliente_id == c.cliente_id), None
            )
            margem_atual = linha_correspondente.margem_pct if linha_correspondente else 0.0
            if margem_atual < 30:
                recomendacao = "renegociar_urgente"
                reajuste = 25.0
            elif margem_atual < 55:
                recomendacao = "reajustar"
                reajuste = 10.0
            else:
                recomendacao = "manter"
                reajuste = None
            renovacoes.append(
                RenovacaoProxima(
                    cliente_id=c.cliente_id,
                    cliente_nome=c.cliente.nome,
                    vencimento=c.vigencia_fim,
                    dias_restantes=dias,
                    margem_atual_pct=margem_atual,
                    recomendacao=recomendacao,  # type: ignore[arg-type]
                    reajuste_sugerido_pct=reajuste,
                )
            )

    renovacoes.sort(key=lambda r: r.dias_restantes)

    return DashboardExecutivo(
        gerado_em=datetime.now(UTC),
        mes_referencia=_label_mes_pt(inicio),
        kpi_hero=kpi_hero,
        contratos=linhas,
        projecao_12m=projecao,
        kpi_operacional=kpi_op,
        alertas=alertas,
        renovacoes_proximas=renovacoes,
        receita_prevista_centavos=receita_prevista,
        margem_prevista_centavos=margem_prevista,
        operacao_mes=operacao_mes,
        pipeline_hospitais=pipeline_hospitais,
        sem_contratos_configurados=len(contratos) == 0,
    )


def _label_mes_pt(d: date) -> str:
    """Retorna 'Junho/2026' a partir de uma data."""
    nomes = [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    return f"{nomes[d.month - 1]}/{d.year}"


def _label_mes_pt_curto(d: date) -> str:
    nomes = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    return f"{nomes[d.month - 1]}/{str(d.year)[2:]}"


def _montar_projecao_12m(
    receita_atual: int, meta: int, hoje: date
) -> list[ProjecaoMensal]:
    """Projeção simples: 3 meses passados + atual + 8 futuros.

    No futuro: regressão linear sobre histórico real.
    """
    proj: list[ProjecaoMensal] = []
    base = _inicio_mes(hoje)
    crescimento = 1.05  # 5% mês — heurística inicial

    for offset in range(-3, 9):
        mes_inicio = base
        # ajusta offset
        for _ in range(abs(offset)):
            if offset < 0:
                mes_inicio = _inicio_mes(mes_inicio - timedelta(days=1))
            else:
                mes_inicio = _proximo_mes(mes_inicio)
        # Receita projetada
        if offset == 0:
            receita = receita_atual
        elif offset < 0:
            receita = round(receita_atual / (crescimento ** abs(offset)))
        else:
            receita = round(receita_atual * (crescimento ** offset))
        proj.append(
            ProjecaoMensal(
                mes=_label_mes_pt_curto(mes_inicio),
                receita_centavos=receita,
                meta_centavos=meta,
                realizado=offset <= 0,
            )
        )
    return proj


def _scope_lote(stmt, tenant_id: UUID | None):  # type: ignore[no-untyped-def]
    """Aplica filtro de tenant numa query de Lote, quando houver tenant."""
    if tenant_id is not None:
        stmt = stmt.where(Lote.cliente_id == tenant_id)
    return stmt


async def _kpi_hero_scp(
    db: AsyncSession,
    tenant_id: UUID,
    inicio: date,
    *,
    fallback: KPIHero,
) -> KPIHero:
    """KPI Hero a partir da apuração SCP do mês (modelo repasse/SCP).

    Se não houver apuração na competência, devolve o `fallback` (que veio
    dos contratos — normalmente zerado pra repasse, e tudo bem).
    """
    competencia = f"{inicio.year:04d}-{inicio.month:02d}"
    ap = await db.scalar(
        select(ApuracaoSCP).where(
            ApuracaoSCP.cliente_id == tenant_id,
            ApuracaoSCP.competencia == competencia,
        )
    )
    if ap is None:
        return fallback

    receita = ap.receita_bruta_centavos or 0
    custo = ap.custos_centavos or 0
    lucro = ap.resultado_centavos if ap.resultado_centavos is not None else (receita - custo)
    margem = (lucro / receita * 100) if receita > 0 else 0.0
    meta = fallback.meta_total_centavos
    return KPIHero(
        lucro_liquido_centavos=lucro,
        receita_total_centavos=receita,
        custo_total_centavos=custo,
        margem_media_pct=round(margem, 2),
        delta_lucro_pct=0.0,
        meta_total_centavos=meta,
        meta_atingida_pct=round((receita / meta * 100), 2) if meta > 0 else 0.0,
    )


async def _kpi_operacional(
    db: AsyncSession, inicio: date, fim: date, tenant_id: UUID | None = None
) -> KPIOperacional:
    """KPIs operacionais do mês (lotes, tempo médio, taxa erro, conciliação)."""
    inicio_dt = datetime.combine(inicio, datetime.min.time(), UTC)
    fim_dt = datetime.combine(fim, datetime.min.time(), UTC)

    # Lotes processados (qualquer status do mês)
    qtd_processados = (
        await db.scalar(
            _scope_lote(
                select(func.count(Lote.id)).where(
                    Lote.created_at >= inicio_dt, Lote.created_at < fim_dt
                ),
                tenant_id,
            )
        )
    ) or 0
    qtd_aguardando = (
        await db.scalar(
            _scope_lote(
                select(func.count(Lote.id)).where(
                    Lote.status == StatusLote.AGUARDANDO_REVISAO
                ),
                tenant_id,
            )
        )
    ) or 0
    pgto_mes = (
        await db.scalar(
            _scope_lote(
                select(func.coalesce(func.sum(Lote.total_pagamentos), 0)).where(
                    Lote.created_at >= inicio_dt,
                    Lote.created_at < fim_dt,
                    Lote.status.in_(
                        [
                            StatusLote.APROVADO,
                            StatusLote.ENVIADO_BANCO,
                            StatusLote.CONCILIADO,
                        ]
                    ),
                ),
                tenant_id,
            )
        )
    ) or 0
    bloqueados = (
        await db.scalar(
            _scope_lote(
                select(func.coalesce(func.sum(Lote.total_bloqueados), 0)).where(
                    Lote.created_at >= inicio_dt, Lote.created_at < fim_dt
                ),
                tenant_id,
            )
        )
    ) or 0
    total_pgto = (
        await db.scalar(
            _scope_lote(
                select(func.coalesce(func.sum(Lote.total_pagamentos), 0)).where(
                    Lote.created_at >= inicio_dt, Lote.created_at < fim_dt
                ),
                tenant_id,
            )
        )
    ) or 0
    taxa_erro = (bloqueados / total_pgto * 100) if total_pgto > 0 else 0.0

    conciliados = (
        await db.scalar(
            _scope_lote(
                select(func.count(Lote.id)).where(
                    Lote.created_at >= inicio_dt,
                    Lote.created_at < fim_dt,
                    Lote.status == StatusLote.CONCILIADO,
                ),
                tenant_id,
            )
        )
    ) or 0
    enviados = (
        await db.scalar(
            _scope_lote(
                select(func.count(Lote.id)).where(
                    Lote.created_at >= inicio_dt,
                    Lote.created_at < fim_dt,
                    Lote.status.in_(
                        [StatusLote.ENVIADO_BANCO, StatusLote.CONCILIADO]
                    ),
                ),
                tenant_id,
            )
        )
    ) or 0
    conciliados_pct = (conciliados / enviados * 100) if enviados > 0 else 0.0

    return KPIOperacional(
        lotes_processados=qtd_processados,
        lotes_aguardando=qtd_aguardando,
        tempo_medio_processamento_min=12.0,  # placeholder; TODO: medir real
        taxa_erro_pct=round(taxa_erro, 2),
        pagamentos_mes=int(pgto_mes),
        conciliados_pct=round(conciliados_pct, 2),
    )


async def _pipeline_completo(
    db: AsyncSession,
    inicio: date,
    fim: date,
    contratos: list[ContratoHospital],
    tenant_id: UUID | None = None,
) -> tuple[ResumoOperacaoMes, list[ResumoPipelineHospital]]:
    """Agrega "programação de pagamento" vs "pagamentos realizados" do mês.

    A diferença pra `_query_volume_por_cliente` (que vai pra cálculo de
    receita do contrato) é que aqui o objetivo é mostrar TUDO que está
    em movimento — mesmo sem contrato configurado. Isso garante que o
    Executivo nunca fica em branco quando há atividade no sistema.

    Programação:  fichas pendentes + lotes em revisão/aprovados
    Realizado:    lotes enviados ao banco / conciliados
    """
    inicio_dt = datetime.combine(inicio, datetime.min.time(), UTC)
    fim_dt = datetime.combine(fim, datetime.min.time(), UTC)

    contratos_por_cliente = {c.cliente_id: c for c in contratos}

    # Carrega clientes (escopado por tenant quando houver)
    clientes_stmt = select(Cliente).order_by(Cliente.nome)
    if tenant_id is not None:
        clientes_stmt = clientes_stmt.where(Cliente.id == tenant_id)
    clientes_q = await db.execute(clientes_stmt)
    clientes = list(clientes_q.scalars().all())
    clientes_por_id = {c.id: c for c in clientes}

    # Lotes do mês agrupados por status + cliente
    lotes_stmt = (
        select(
            Lote.cliente_id,
            Lote.status,
            func.count(Lote.id).label("qtd"),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0).label("total"),
            func.max(Lote.created_at).label("ultima"),
        )
        .where(
            Lote.created_at >= inicio_dt,
            Lote.created_at < fim_dt,
        )
        .group_by(Lote.cliente_id, Lote.status)
    )
    if tenant_id is not None:
        lotes_stmt = lotes_stmt.where(Lote.cliente_id == tenant_id)
    lotes_q = await db.execute(lotes_stmt)

    # estrutura: agregador[cliente_id][bucket] = (qtd, valor)
    agregador: dict[UUID, dict[str, tuple[int, int]]] = defaultdict(dict)
    ultima_atividade_por_cliente: dict[UUID, datetime] = {}

    for row in lotes_q:
        cid = row.cliente_id
        status_lote = row.status
        qtd = int(row.qtd or 0)
        valor = int(row.total or 0)

        if status_lote in (StatusLote.AGUARDANDO_REVISAO,):
            bucket = "revisao"
        elif status_lote in (StatusLote.APROVADO, StatusLote.PROCESSANDO):
            bucket = "aprovado"
        elif status_lote == StatusLote.ENVIADO_BANCO:
            bucket = "enviado"
        elif status_lote == StatusLote.CONCILIADO:
            bucket = "conciliado"
        else:
            continue

        atual_qtd, atual_valor = agregador[cid].get(bucket, (0, 0))
        agregador[cid][bucket] = (atual_qtd + qtd, atual_valor + valor)
        if row.ultima:
            ant = ultima_atividade_por_cliente.get(cid)
            if not ant or row.ultima > ant:
                ultima_atividade_por_cliente[cid] = row.ultima

    # Fichas pendentes (extraídas/revisadas que ainda NÃO viraram lote)
    # Carregamos as fichas pra somar valor em Python — `valor_total_centavos`
    # é uma @property derivada de `linhas_extraidas` (JSON), não coluna SQL.
    fichas_pend_stmt = select(FichaPlantao).where(
        FichaPlantao.created_at >= inicio_dt,
        FichaPlantao.created_at < fim_dt,
        FichaPlantao.status.in_(
            [StatusFicha.EXTRAIDA, StatusFicha.REVISADA]
        ),
        FichaPlantao.lote_gerado_id.is_(None),
    )
    if tenant_id is not None:
        fichas_pend_stmt = fichas_pend_stmt.where(
            FichaPlantao.cliente_id == tenant_id
        )
    fichas_pend_q = await db.execute(fichas_pend_stmt)
    fichas_pend = list(fichas_pend_q.scalars().all())
    fichas_por_cliente: dict[UUID, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for f in fichas_pend:
        atual_qtd, atual_valor = fichas_por_cliente[f.cliente_id]
        fichas_por_cliente[f.cliente_id] = (
            atual_qtd + 1,
            atual_valor + (f.valor_total_centavos or 0),
        )
        ant = ultima_atividade_por_cliente.get(f.cliente_id)
        if not ant or f.created_at > ant:
            ultima_atividade_por_cliente[f.cliente_id] = f.created_at

    # Quem é "ativo" no mês? Quem tem lote OU ficha pendente
    cliente_ids_ativos = set(agregador.keys()) | set(fichas_por_cliente.keys())

    pipelines: list[ResumoPipelineHospital] = []
    total_ficha_qtd = 0
    total_ficha_valor = 0
    total_revisao_qtd = 0
    total_revisao_valor = 0
    total_aprovado_qtd = 0
    total_aprovado_valor = 0
    total_enviado_qtd = 0
    total_enviado_valor = 0
    total_conciliado_qtd = 0
    total_conciliado_valor = 0

    for cid in cliente_ids_ativos:
        cliente = clientes_por_id.get(cid)
        if cliente is None:
            continue
        buckets = agregador.get(cid, {})
        revisao_qtd, revisao_valor = buckets.get("revisao", (0, 0))
        aprovado_qtd, aprovado_valor = buckets.get("aprovado", (0, 0))
        enviado_qtd, enviado_valor = buckets.get("enviado", (0, 0))
        conciliado_qtd, conciliado_valor = buckets.get("conciliado", (0, 0))
        ficha_qtd, ficha_valor = fichas_por_cliente.get(cid, (0, 0))

        volume_total = (
            ficha_valor + revisao_valor + aprovado_valor + enviado_valor + conciliado_valor
        )

        pipelines.append(
            ResumoPipelineHospital(
                cliente_id=cid,
                cliente_nome=cliente.nome,
                tem_contrato=cid in contratos_por_cliente,
                fichas_pendentes=ficha_qtd,
                valor_fichas_pendentes_centavos=ficha_valor,
                lotes_em_revisao=revisao_qtd,
                valor_lotes_em_revisao_centavos=revisao_valor,
                lotes_aprovados=aprovado_qtd,
                valor_lotes_aprovados_centavos=aprovado_valor,
                lotes_enviados=enviado_qtd,
                valor_lotes_enviados_centavos=enviado_valor,
                lotes_conciliados=conciliado_qtd,
                valor_lotes_conciliados_centavos=conciliado_valor,
                volume_total_mes_centavos=volume_total,
                ultima_atividade=ultima_atividade_por_cliente.get(cid),
            )
        )

        total_ficha_qtd += ficha_qtd
        total_ficha_valor += ficha_valor
        total_revisao_qtd += revisao_qtd
        total_revisao_valor += revisao_valor
        total_aprovado_qtd += aprovado_qtd
        total_aprovado_valor += aprovado_valor
        total_enviado_qtd += enviado_qtd
        total_enviado_valor += enviado_valor
        total_conciliado_qtd += conciliado_qtd
        total_conciliado_valor += conciliado_valor

    pipelines.sort(key=lambda p: p.volume_total_mes_centavos, reverse=True)

    operacao = ResumoOperacaoMes(
        qtd_fichas_pendentes=total_ficha_qtd,
        valor_fichas_pendentes_centavos=total_ficha_valor,
        qtd_lotes_programados=total_revisao_qtd + total_aprovado_qtd,
        valor_lotes_programados_centavos=total_revisao_valor + total_aprovado_valor,
        qtd_lotes_enviados=total_enviado_qtd,
        valor_lotes_enviados_centavos=total_enviado_valor,
        qtd_lotes_conciliados=total_conciliado_qtd,
        valor_lotes_conciliados_centavos=total_conciliado_valor,
        volume_total_mes_centavos=(
            total_ficha_valor
            + total_revisao_valor
            + total_aprovado_valor
            + total_enviado_valor
            + total_conciliado_valor
        ),
        qtd_clientes_ativos=len(cliente_ids_ativos),
    )

    return operacao, pipelines


async def _pipeline_fichas(
    db: AsyncSession, inicio: date, fim: date, tenant_id: UUID | None = None
) -> tuple[int, int]:
    """Receita prevista vinda das fichas em pipeline (não viraram lote ainda).

    Soma valor das fichas EXTRAÍDA + REVISADA do mês (que ainda virariam
    lote em breve). Margem = receita × 0.6 (heurística inicial — depois
    refina aplicando contrato).
    """
    inicio_dt = datetime.combine(inicio, datetime.min.time(), UTC)
    fim_dt = datetime.combine(fim, datetime.min.time(), UTC)

    # `valor_total_centavos` é @property derivada de `linhas_extraidas` (JSON),
    # então precisamos somar em Python.
    fichas_stmt = select(FichaPlantao).where(
        FichaPlantao.created_at >= inicio_dt,
        FichaPlantao.created_at < fim_dt,
        FichaPlantao.status.in_(
            [StatusFicha.EXTRAIDA, StatusFicha.REVISADA]
        ),
        FichaPlantao.lote_gerado_id.is_(None),
    )
    if tenant_id is not None:
        fichas_stmt = fichas_stmt.where(FichaPlantao.cliente_id == tenant_id)
    fichas_q = await db.execute(fichas_stmt)
    fichas = list(fichas_q.scalars().all())
    valor = sum(f.valor_total_centavos or 0 for f in fichas)
    margem_estimada = round(valor * 0.6)
    return valor, margem_estimada


# ============================================================
# Painel do Coordenador — banco de horas / extrato
# ============================================================


@router.get("/coordenador/meu-painel", response_model=PainelCoordenadorOut)
async def meu_painel_coordenador(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PainelCoordenadorOut:
    """Visão restrita do coordenador.

    Lista as fichas que ele subiu, calcula um "banco de horas" agregando
    por médico (CPF) — assim ele percebe se acidentalmente subiu a
    mesma operação 2x.
    """
    # Aceita só COORDENADOR ou roles superiores (admin pode olhar pra
    # auditoria de quem está duplicando).
    if current_user.role not in {
        UserRole.COORDENADOR,
        UserRole.OPERADOR,
        UserRole.APROVADOR,
        UserRole.ADMIN,
    }:
        raise PermissaoNegadaError("Sem permissão de coordenador")

    # Filtra pelo usuário (coordenador só vê o próprio; admin/aprovador
    # vê o próprio também — pra ver de outro tem outras telas).
    fichas_q = await db.execute(
        select(FichaPlantao)
        .where(FichaPlantao.enviado_por_id == current_user.id)
        .options(selectinload(FichaPlantao.cliente))
        .order_by(FichaPlantao.created_at.desc())
        .limit(100)
    )
    fichas = list(fichas_q.scalars().all())

    hoje = datetime.now(tz=UTC).date()
    inicio = _inicio_mes(hoje)
    inicio_dt = datetime.combine(inicio, datetime.min.time(), UTC)

    # Detecção de duplicidade baseada em hash do arquivo (mesma ficha
    # subida 2x) E em assinatura "cliente + competência" (subiu 2 fichas
    # do mesmo hospital no mesmo mês).
    hash_seen: dict[str, UUID] = {}
    sig_seen: dict[tuple[UUID, str], UUID] = {}
    duplicatas_count = 0
    fichas_resumo: list[FichaCoordenadorResumo] = []

    for f in fichas:
        competencia = (f.metadados or {}).get("competencia") if f.metadados else None
        duplicada_de: UUID | None = None
        motivo: str | None = None

        if f.hash_arquivo and f.hash_arquivo in hash_seen:
            duplicada_de = hash_seen[f.hash_arquivo]
            motivo = "Mesmo arquivo já enviado anteriormente"
        elif competencia:
            sig = (f.cliente_id, competencia)
            if sig in sig_seen:
                duplicada_de = sig_seen[sig]
                motivo = (
                    f"Já existe ficha do mesmo hospital pra {competencia}. "
                    "Confira antes de aprovar."
                )
            else:
                sig_seen[sig] = f.id

        if f.hash_arquivo:
            hash_seen.setdefault(f.hash_arquivo, f.id)

        if duplicada_de:
            duplicatas_count += 1

        fichas_resumo.append(
            FichaCoordenadorResumo(
                id=f.id,
                cliente_nome=f.cliente.nome,
                nome_arquivo=f.nome_arquivo,
                competencia=competencia,
                status=f.status.value,
                total_linhas=f.total_linhas,
                valor_total_centavos=f.valor_total_centavos,
                created_at=f.created_at,
                duplicada_de_id=duplicada_de,
                motivo_duplicidade=motivo,
            )
        )

    # Banco de horas — agrega por CPF (mascarado pra UI)
    agregador: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "nome": "",
            "qtd_fichas": 0,
            "horas_total": 0,
            "valor_total_centavos": 0,
            "competencias": set(),
            "ultima_ficha_id": None,
            "ultima_ficha_em": None,
        }
    )
    for f in fichas:
        for linha in f.linhas_extraidas or []:
            cpf = linha.get("cpf")
            if not cpf:
                continue
            cpf_str = str(cpf)
            mascarado = (
                f"{cpf_str[:3]}.***.{cpf_str[-2:]}" if len(cpf_str) >= 5 else "***"
            )
            entry = agregador[cpf_str]
            entry["nome"] = entry["nome"] or linha.get("nome", "—")
            entry["qtd_fichas"] += 1
            entry["horas_total"] += int(linha.get("horas") or 0)
            entry["valor_total_centavos"] += int(linha.get("valor_centavos") or 0)
            comp = (f.metadados or {}).get("competencia") if f.metadados else None
            if comp:
                entry["competencias"].add(comp)
            if (
                entry["ultima_ficha_em"] is None
                or f.created_at > entry["ultima_ficha_em"]
            ):
                entry["ultima_ficha_em"] = f.created_at
                entry["ultima_ficha_id"] = f.id
            entry["__cpf_mask__"] = mascarado

    banco_horas: list[BancoHorasMedico] = []
    for cpf_str, dados in agregador.items():
        banco_horas.append(
            BancoHorasMedico(
                cpf_mascarado=dados.get("__cpf_mask__", "***"),
                nome=dados["nome"] or "—",
                qtd_fichas=dados["qtd_fichas"],
                horas_total=dados["horas_total"],
                valor_total_centavos=dados["valor_total_centavos"],
                competencias=sorted(dados["competencias"]),
                ultima_ficha_id=dados["ultima_ficha_id"],
                ultima_ficha_em=dados["ultima_ficha_em"],
            )
        )
    # Ordena: maior valor primeiro (gestor enxerga primeiro o crítico)
    banco_horas.sort(key=lambda x: x.valor_total_centavos, reverse=True)

    # Métricas-resumo
    qtd_total = len(fichas)
    qtd_mes = sum(1 for f in fichas if f.created_at >= inicio_dt)
    qtd_lotes = sum(1 for f in fichas if f.lote_gerado_id is not None)
    valor_mes = sum(
        f.valor_total_centavos for f in fichas if f.created_at >= inicio_dt
    )

    return PainelCoordenadorOut(
        gerado_em=datetime.now(UTC),
        fichas_recentes=fichas_resumo[:30],
        banco_horas=banco_horas[:50],
        qtd_fichas_total=qtd_total,
        qtd_fichas_mes=qtd_mes,
        qtd_lotes_gerados=qtd_lotes,
        valor_total_mes_centavos=valor_mes,
        duplicatas_potenciais=duplicatas_count,
    )
