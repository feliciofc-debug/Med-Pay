"""Endpoints do Extrato Consolidado.

GET  /api/consolidacao/clientes-com-fichas
GET  /api/consolidacao/competencias?cliente_id=...
GET  /api/consolidacao/hospital-mes?cliente_id=...&competencia=06/2026
GET  /api/consolidacao/dia?cliente_id=...&data=2026-05-28
GET  /api/consolidacao/medico?cliente_id=...&beneficiario_id=... (ou &cpf=...)
POST /api/consolidacao/gerar-lote   → cria lote único das N fichas escolhidas

Acesso:
    - Visualização (GETs): visão executiva — ADMIN, APROVADOR, OPERADOR,
      GESTOR e FINANCEIRO (COORDENADOR/MÉDICO ficam de fora).
    - gerar-lote (POST): quem executa pagamento — APROVADOR/ADMIN (BPO) e
      GESTOR de tenant com `pagamento.execucao` (empresa de repasse/SCP).
Tudo escopado por tenant (próprio cliente ou hospital-filho na carteira).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_db,
    require_execucao_pagamento,
    require_visao_executiva,
    verificar_acesso_cliente,
)
from app.models.user import User
from app.schemas.consolidacao import (
    ClienteComFichasOut,
    ExtratoConsolidadoOut,
    GerarLoteConsolidadoRequest,
    GerarLoteConsolidadoResposta,
)
from app.services.consolidacao_service import (
    consolidar_por_dia,
    consolidar_por_hospital_mes,
    consolidar_por_medico,
    gerar_lote_consolidado,
    listar_clientes_com_fichas_pendentes,
    listar_competencias_disponiveis,
)

router = APIRouter()


@router.get(
    "/clientes-com-fichas",
    response_model=list[ClienteComFichasOut],
)
async def listar_clientes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
) -> list[ClienteComFichasOut]:
    items = await listar_clientes_com_fichas_pendentes(db)
    # Multi-tenancy: filtra resultado pra mostrar só o próprio cliente
    if user.cliente_id is not None:
        items = [t for t in items if t[0] == user.cliente_id]
    return [
        ClienteComFichasOut(
            cliente_id=cid, nome=nome, qtd_fichas_pendentes=qtd
        )
        for cid, nome, qtd in items
    ]


@router.get("/competencias", response_model=list[str])
async def listar_competencias(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
) -> list[str]:
    await verificar_acesso_cliente(db, user, cliente_id)
    return await listar_competencias_disponiveis(db, cliente_id=cliente_id)


@router.get("/hospital-mes", response_model=ExtratoConsolidadoOut)
async def por_hospital_mes(
    cliente_id: UUID,
    competencia: str | None = Query(None, description="MM/YYYY"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
) -> ExtratoConsolidadoOut:
    await verificar_acesso_cliente(db, user, cliente_id)
    extrato = await consolidar_por_hospital_mes(
        db, cliente_id=cliente_id, competencia=competencia
    )
    return ExtratoConsolidadoOut.model_validate(extrato)


@router.get("/dia", response_model=ExtratoConsolidadoOut)
async def por_dia(
    cliente_id: UUID,
    data: datetime = Query(..., description="ISO date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
) -> ExtratoConsolidadoOut:
    await verificar_acesso_cliente(db, user, cliente_id)
    extrato = await consolidar_por_dia(db, cliente_id=cliente_id, data=data)
    return ExtratoConsolidadoOut.model_validate(extrato)


@router.get("/medico", response_model=ExtratoConsolidadoOut)
async def por_medico(
    cliente_id: UUID,
    beneficiario_id: UUID | None = None,
    cpf: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
) -> ExtratoConsolidadoOut:
    await verificar_acesso_cliente(db, user, cliente_id)
    extrato = await consolidar_por_medico(
        db,
        cliente_id=cliente_id,
        beneficiario_id=beneficiario_id,
        cpf=cpf,
    )
    return ExtratoConsolidadoOut.model_validate(extrato)


@router.post(
    "/gerar-lote",
    response_model=GerarLoteConsolidadoResposta,
    status_code=201,
)
async def gerar_lote(
    payload: GerarLoteConsolidadoRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_execucao_pagamento),
) -> GerarLoteConsolidadoResposta:
    lote = await gerar_lote_consolidado(
        db,
        fichas_ids=payload.fichas_ids,
        usuario=user,
        referencia=payload.referencia,
    )
    return GerarLoteConsolidadoResposta(
        lote_id=lote.id,
        status=lote.status.value,
        total_pagamentos=lote.total_pagamentos or 0,
        valor_total_centavos=lote.valor_total_centavos or 0,
    )
