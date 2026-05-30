"""Aportes recebidos por hospital — rastreio dos depósitos da carteira.

A empresa de repasse registra aqui quanto cada hospital depositou (e em
qual conta). O saldo confirmado é o que "libera" a distribuição daquele
hospital: só se paga o que entrou.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    cliente_ids_acessiveis,
    get_current_user,
    get_db,
    require_execucao_pagamento,
    verificar_acesso_cliente,
)
from app.core.exceptions import LoteNaoEncontradoError
from app.models.aporte import AporteHospital, StatusAporte
from app.models.cliente import Cliente
from app.models.user import User

router = APIRouter(prefix="/api/aportes", tags=["aportes"])
log = structlog.get_logger()


# ============================================================
# Schemas
# ============================================================


class AporteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    cliente_nome: str | None = None
    conta_pagadora_id: UUID | None
    lote_id: UUID | None
    valor_centavos: int
    data_recebimento: date
    competencia: str | None
    referencia: str | None
    status: StatusAporte


class CriarAporteRequest(BaseModel):
    cliente_id: UUID
    conta_pagadora_id: UUID | None = None
    lote_id: UUID | None = None
    valor_centavos: int = Field(gt=0)
    data_recebimento: date
    competencia: str | None = Field(default=None, max_length=7)
    referencia: str | None = Field(default=None, max_length=255)


class SaldoAporteOut(BaseModel):
    cliente_id: UUID
    recebido_confirmado_centavos: int
    recebido_pendente_centavos: int
    liberado: bool


# ============================================================
# Endpoints
# ============================================================


@router.get("", response_model=list[AporteOut])
async def listar_aportes(
    cliente_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AporteOut]:
    """Lista aportes dos hospitais que o usuário pode acessar."""
    permitidos = await cliente_ids_acessiveis(db, current_user)

    stmt = (
        select(AporteHospital, Cliente.nome)
        .join(Cliente, Cliente.id == AporteHospital.cliente_id)
        .order_by(AporteHospital.data_recebimento.desc())
    )
    if cliente_id is not None:
        await verificar_acesso_cliente(db, current_user, cliente_id)
        stmt = stmt.where(AporteHospital.cliente_id == cliente_id)
    elif permitidos is not None:
        stmt = stmt.where(AporteHospital.cliente_id.in_(permitidos))

    result = await db.execute(stmt)
    out: list[AporteOut] = []
    for aporte, nome in result.all():
        item = AporteOut.model_validate(aporte)
        item.cliente_nome = nome
        out.append(item)
    return out


@router.post("", response_model=AporteOut, status_code=201)
async def registrar_aporte(
    payload: CriarAporteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> AporteOut:
    """Registra um aporte recebido de um hospital da carteira."""
    await verificar_acesso_cliente(db, current_user, payload.cliente_id)

    aporte = AporteHospital(
        cliente_id=payload.cliente_id,
        conta_pagadora_id=payload.conta_pagadora_id,
        lote_id=payload.lote_id,
        valor_centavos=payload.valor_centavos,
        data_recebimento=payload.data_recebimento,
        competencia=payload.competencia,
        referencia=payload.referencia,
        status=StatusAporte.PENDENTE,
    )
    db.add(aporte)
    await db.flush()
    await db.refresh(aporte)
    log.info("aporte.registrado", aporte_id=str(aporte.id), cliente_id=str(payload.cliente_id))
    return AporteOut.model_validate(aporte)


@router.post("/{aporte_id}/confirmar", response_model=AporteOut)
async def confirmar_aporte(
    aporte_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> AporteOut:
    """Confirma que o dinheiro bateu na conta (libera o pagamento)."""
    aporte = await db.get(AporteHospital, aporte_id)
    if aporte is None:
        raise LoteNaoEncontradoError("Aporte não encontrado")
    await verificar_acesso_cliente(db, current_user, aporte.cliente_id)
    aporte.status = StatusAporte.CONFIRMADO
    await db.flush()
    await db.refresh(aporte)
    log.info("aporte.confirmado", aporte_id=str(aporte.id))
    return AporteOut.model_validate(aporte)


@router.get("/saldo", response_model=SaldoAporteOut)
async def saldo_aporte(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SaldoAporteOut:
    """Saldo recebido (confirmado vs pendente) de um hospital."""
    await verificar_acesso_cliente(db, current_user, cliente_id)

    async def _soma(status: StatusAporte) -> int:
        r = await db.execute(
            select(func.coalesce(func.sum(AporteHospital.valor_centavos), 0)).where(
                AporteHospital.cliente_id == cliente_id,
                AporteHospital.status == status,
            )
        )
        return int(r.scalar_one())

    confirmado = await _soma(StatusAporte.CONFIRMADO)
    pendente = await _soma(StatusAporte.PENDENTE)
    return SaldoAporteOut(
        cliente_id=cliente_id,
        recebido_confirmado_centavos=confirmado,
        recebido_pendente_centavos=pendente,
        liberado=confirmado > 0,
    )


__all__ = ["router"]
