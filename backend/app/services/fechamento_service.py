"""Service de Fechamento de Período por Hospital.

O fechamento é o "trancamento" formal de um mês operacional de um
hospital. Ele transforma o monte de fichas pendentes da competência
em um snapshot persistido (`FechamentoPeriodo`), que vira depois um
extrato pro contador/RH e/ou um Lote de pagamento.

Fluxo típico:

    1. Gestor chama `preview` pra ver o que ENTRA no fechamento
       (sem gravar nada). Mostra: X fichas, Y médicos, R$ Z.
    2. Gestor confere e chama `trancar` pra criar o fechamento.
       Snapshot é gravado. Fichas continuam intactas (ainda em
       EXTRAIDA/REVISADA) — o que muda é que agora têm um
       FechamentoPeriodo "pai" amarrando elas a um período fechado.
    3. Financeiro chama `gerar_lote` que usa o `gerar_lote_consolidado`
       existente — vira um Lote único pronto pra aprovar e pagar.
    4. Gestor pode `reabrir` se ainda não gerou lote.

Multi-tenant:
    Todas as queries filtram por `cliente_id`. Quem chama é
    responsável por passar o `cliente_id` correto (via `get_tenant_id`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import MedPagException, ValidacaoError
from app.models.fechamento_periodo import (
    FechamentoPeriodo,
    StatusFechamento,
)
from app.models.user import User
from app.services import consolidacao_service

log = structlog.get_logger()


class FechamentoNaoEncontradoError(MedPagException):
    code = "FECHAMENTO_NAO_ENCONTRADO"
    status_code = 404


class FechamentoJaExisteError(MedPagException):
    code = "FECHAMENTO_JA_EXISTE"
    status_code = 409


class FechamentoBloqueadoError(MedPagException):
    """Não dá pra reabrir fechamento que já virou lote."""

    code = "FECHAMENTO_BLOQUEADO"
    status_code = 409


def _validar_competencia(ano: int, mes: int) -> None:
    if mes < 1 or mes > 12:
        raise ValidacaoError(f"Mês inválido: {mes} (precisa estar entre 1 e 12)")
    if ano < 2020 or ano > 2100:
        raise ValidacaoError(f"Ano inválido: {ano}")


def _competencia_str(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


# ============================================================
# Preview (não persiste)
# ============================================================


async def preview_fechamento(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    ano: int,
    mes: int,
):
    """Mostra o que entraria no fechamento, sem persistir.

    Retorna o ExtratoConsolidado da competência (delegando pro
    consolidacao_service). Útil pro gestor "ver antes de trancar".
    """
    _validar_competencia(ano, mes)
    competencia = _competencia_str(ano, mes)
    return await consolidacao_service.consolidar_por_hospital_mes(
        db, cliente_id=cliente_id, competencia=competencia
    )


# ============================================================
# Listar
# ============================================================


async def listar_fechamentos(
    db: AsyncSession,
    *,
    cliente_id: UUID | None = None,
    ano: int | None = None,
    limit: int = 50,
) -> list[FechamentoPeriodo]:
    """Lista fechamentos (ordenados do mais recente pro mais antigo).

    Se `cliente_id` for None, lista de TODOS os tenants — só usar em
    contexto MedPag interno.
    """
    q = select(FechamentoPeriodo).options(
        selectinload(FechamentoPeriodo.cliente),
        selectinload(FechamentoPeriodo.lote),
        selectinload(FechamentoPeriodo.trancado_por),
    )
    if cliente_id:
        q = q.where(FechamentoPeriodo.cliente_id == cliente_id)
    if ano:
        q = q.where(FechamentoPeriodo.ano == ano)
    q = q.order_by(
        FechamentoPeriodo.ano.desc(),
        FechamentoPeriodo.mes.desc(),
        FechamentoPeriodo.created_at.desc(),
    ).limit(limit)

    result = await db.execute(q)
    return list(result.scalars())


async def obter_fechamento(
    db: AsyncSession,
    fechamento_id: UUID,
    *,
    cliente_id: UUID | None = None,
) -> FechamentoPeriodo:
    """Busca fechamento por id, opcionalmente validando tenant."""
    q = (
        select(FechamentoPeriodo)
        .where(FechamentoPeriodo.id == fechamento_id)
        .options(
            selectinload(FechamentoPeriodo.cliente),
            selectinload(FechamentoPeriodo.lote),
            selectinload(FechamentoPeriodo.trancado_por),
            selectinload(FechamentoPeriodo.reaberto_por),
        )
    )
    if cliente_id:
        q = q.where(FechamentoPeriodo.cliente_id == cliente_id)

    result = await db.execute(q)
    fechamento = result.scalar_one_or_none()
    if fechamento is None:
        raise FechamentoNaoEncontradoError(
            f"Fechamento {fechamento_id} não encontrado"
        )
    return fechamento


async def buscar_fechamento_existente(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    ano: int,
    mes: int,
) -> FechamentoPeriodo | None:
    q = select(FechamentoPeriodo).where(
        FechamentoPeriodo.cliente_id == cliente_id,
        FechamentoPeriodo.ano == ano,
        FechamentoPeriodo.mes == mes,
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


# ============================================================
# Trancar (cria o fechamento com snapshot)
# ============================================================


async def trancar_periodo(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    ano: int,
    mes: int,
    user: User,
    observacoes: str | None = None,
) -> FechamentoPeriodo:
    """Tranca um período pra um hospital.

    - Calcula o snapshot usando consolidar_por_hospital_mes
    - Cria registro FechamentoPeriodo em status TRANCADO
    - Falha se já existe um fechamento pro mesmo cliente/ano/mes
    """
    _validar_competencia(ano, mes)

    existente = await buscar_fechamento_existente(
        db, cliente_id=cliente_id, ano=ano, mes=mes
    )
    if existente is not None:
        raise FechamentoJaExisteError(
            f"Já existe um fechamento para {_competencia_str(ano, mes)} "
            f"(status: {existente.status.value}). "
            "Reabra antes se quiser refazer."
        )

    # Snapshot da competência
    extrato = await consolidacao_service.consolidar_por_hospital_mes(
        db, cliente_id=cliente_id, competencia=_competencia_str(ano, mes)
    )

    if extrato.total_fichas == 0:
        raise ValidacaoError(
            f"Nenhuma ficha pendente em {_competencia_str(ano, mes)} "
            "pra trancar. Suba/revise as fichas antes."
        )

    fechamento = FechamentoPeriodo(
        cliente_id=cliente_id,
        ano=ano,
        mes=mes,
        status=StatusFechamento.TRANCADO,
        total_centavos=extrato.valor_total_centavos,
        qtd_fichas=extrato.total_fichas,
        qtd_medicos=extrato.total_medicos_unicos,
        qtd_linhas=extrato.total_linhas,
        trancado_em=datetime.utcnow(),
        trancado_por_id=user.id,
        observacoes=observacoes,
        metadados={
            "fichas_ids": [str(f.id) for f in extrato.fichas],
            "medicos_nao_cadastrados": extrato.medicos_nao_cadastrados,
        },
    )
    db.add(fechamento)
    await db.commit()
    await db.refresh(fechamento)

    log.info(
        "fechamento.trancado",
        cliente_id=str(cliente_id),
        ano=ano,
        mes=mes,
        total_centavos=extrato.valor_total_centavos,
        qtd_fichas=extrato.total_fichas,
        qtd_medicos=extrato.total_medicos_unicos,
        user_id=str(user.id),
    )
    return fechamento


# ============================================================
# Reabrir
# ============================================================


async def reabrir_periodo(
    db: AsyncSession,
    *,
    fechamento_id: UUID,
    user: User,
    cliente_id: UUID | None = None,
) -> FechamentoPeriodo:
    """Reabre um fechamento (volta pra ABERTO).

    Só funciona se o fechamento ainda não virou lote.
    """
    fechamento = await obter_fechamento(
        db, fechamento_id, cliente_id=cliente_id
    )

    if not fechamento.pode_reabrir:
        raise FechamentoBloqueadoError(
            f"Não dá pra reabrir um fechamento em status {fechamento.status.value}. "
            "Cancele o lote primeiro."
        )

    fechamento.status = StatusFechamento.ABERTO
    fechamento.reaberto_em = datetime.utcnow()
    fechamento.reaberto_por_id = user.id
    await db.commit()
    await db.refresh(fechamento)

    log.info(
        "fechamento.reaberto",
        fechamento_id=str(fechamento.id),
        user_id=str(user.id),
    )
    return fechamento


# ============================================================
# Gerar lote a partir do fechamento
# ============================================================


async def gerar_lote_do_fechamento(
    db: AsyncSession,
    *,
    fechamento_id: UUID,
    user: User,
    cliente_id: UUID | None = None,
):
    """Gera um Lote a partir das fichas amarradas a este fechamento.

    Reutiliza `consolidacao_service.gerar_lote_consolidado`. Marca o
    fechamento como GERADO_LOTE.
    """
    fechamento = await obter_fechamento(
        db, fechamento_id, cliente_id=cliente_id
    )

    if fechamento.status != StatusFechamento.TRANCADO:
        raise FechamentoBloqueadoError(
            f"Só dá pra gerar lote de fechamento TRANCADO "
            f"(atual: {fechamento.status.value})"
        )

    ids_fichas = [
        UUID(s) for s in (fechamento.metadados or {}).get("fichas_ids", [])
    ]
    if not ids_fichas:
        raise ValidacaoError(
            "Fechamento sem fichas associadas — nada a gerar."
        )

    lote = await consolidacao_service.gerar_lote_consolidado(
        db,
        fichas_ids=ids_fichas,
        usuario=user,
    )

    fechamento.lote_id = lote.id
    fechamento.status = StatusFechamento.GERADO_LOTE
    await db.commit()
    await db.refresh(fechamento)

    log.info(
        "fechamento.lote_gerado",
        fechamento_id=str(fechamento.id),
        lote_id=str(lote.id),
        user_id=str(user.id),
    )
    return fechamento, lote
