"""Rotas da SCP (modelo MEDPAG_REPASSE).

    GET  /api/scp/{cliente_id}/participantes      → lista sócios participantes
    POST /api/scp/{cliente_id}/participantes      → cadastra participante
    POST /api/scp/{cliente_id}/apuracoes          → cria/atualiza apuração do mês
    GET  /api/scp/apuracoes/{apuracao_id}         → detalhe + distribuições
    POST /api/scp/apuracoes/{apuracao_id}/distribuir → calcula a distribuição

Tudo escopado por cliente (o tenant da SCP). `verificar_acesso_cliente`
garante que o usuário só mexe na própria SCP (admin MedPag passa sempre).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, verificar_acesso_cliente
from app.models.scp import (
    ApuracaoSCP,
    ParticipanteSCP,
    RegraCota,
    StatusApuracaoSCP,
)
from app.models.user import User
from app.services.scp_service import gerar_distribuicao

log = structlog.get_logger()
router = APIRouter()


# ============================================================
# Schemas
# ============================================================


class ParticipanteIn(BaseModel):
    beneficiario_id: UUID
    regra_cota: RegraCota = RegraCota.PROPORCIONAL_SERVICO
    percentual_bp: int = Field(0, ge=0, le=10000, description="Cota fixa em bp (10000=100%)")
    aporte_centavos: int = Field(0, ge=0)
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None


class ParticipanteOut(BaseModel):
    id: UUID
    beneficiario_id: UUID
    beneficiario_nome: str | None = None
    regra_cota: RegraCota
    percentual_bp: int
    aporte_centavos: int
    vigencia_inicio: date
    vigencia_fim: date | None
    ativo: bool


class ApuracaoIn(BaseModel):
    competencia: str = Field(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    receita_bruta_centavos: int = Field(0, ge=0)
    custos_centavos: int = Field(0, ge=0)
    observacoes: str | None = None


class DistribuicaoOut(BaseModel):
    beneficiario_id: UUID
    base_centavos: int
    percentual_aplicado_bp: int
    valor_centavos: int


class ApuracaoOut(BaseModel):
    id: UUID
    cliente_id: UUID
    competencia: str
    receita_bruta_centavos: int
    custos_centavos: int
    resultado_centavos: int
    status: StatusApuracaoSCP
    distribuicoes: list[DistribuicaoOut] = []


class DistribuirIn(BaseModel):
    # beneficiario_id (str) -> valor de serviço no período (centavos).
    bases_servico: dict[str, int] = Field(default_factory=dict)


# ============================================================
# Participantes
# ============================================================


@router.get("/{cliente_id}/participantes", response_model=list[ParticipanteOut])
async def listar_participantes(
    cliente_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ParticipanteOut]:
    await verificar_acesso_cliente(db, user, cliente_id)
    result = await db.execute(
        select(ParticipanteSCP)
        .where(ParticipanteSCP.cliente_id == cliente_id)
        .options(selectinload(ParticipanteSCP.beneficiario))
    )
    parts = result.scalars().all()
    return [
        ParticipanteOut(
            id=p.id,
            beneficiario_id=p.beneficiario_id,
            beneficiario_nome=p.beneficiario.nome if p.beneficiario else None,
            regra_cota=p.regra_cota,
            percentual_bp=p.percentual_bp,
            aporte_centavos=p.aporte_centavos,
            vigencia_inicio=p.vigencia_inicio,
            vigencia_fim=p.vigencia_fim,
            ativo=p.ativo,
        )
        for p in parts
    ]


@router.post("/{cliente_id}/participantes", response_model=ParticipanteOut, status_code=201)
async def criar_participante(
    cliente_id: UUID,
    body: ParticipanteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteOut:
    await verificar_acesso_cliente(db, user, cliente_id)

    part = ParticipanteSCP(
        cliente_id=cliente_id,
        beneficiario_id=body.beneficiario_id,
        regra_cota=body.regra_cota,
        percentual_bp=body.percentual_bp,
        aporte_centavos=body.aporte_centavos,
        vigencia_inicio=body.vigencia_inicio or date.today(),
        vigencia_fim=body.vigencia_fim,
    )
    db.add(part)
    await db.commit()
    await db.refresh(part)
    return ParticipanteOut(
        id=part.id,
        beneficiario_id=part.beneficiario_id,
        beneficiario_nome=None,
        regra_cota=part.regra_cota,
        percentual_bp=part.percentual_bp,
        aporte_centavos=part.aporte_centavos,
        vigencia_inicio=part.vigencia_inicio,
        vigencia_fim=part.vigencia_fim,
        ativo=part.ativo,
    )


# ============================================================
# Apurações
# ============================================================


def _apuracao_para_out(ap: ApuracaoSCP) -> ApuracaoOut:
    return ApuracaoOut(
        id=ap.id,
        cliente_id=ap.cliente_id,
        competencia=ap.competencia,
        receita_bruta_centavos=ap.receita_bruta_centavos,
        custos_centavos=ap.custos_centavos,
        resultado_centavos=ap.resultado_centavos,
        status=ap.status,
        distribuicoes=[
            DistribuicaoOut(
                beneficiario_id=d.beneficiario_id,
                base_centavos=d.base_centavos,
                percentual_aplicado_bp=d.percentual_aplicado_bp,
                valor_centavos=d.valor_centavos,
            )
            for d in sorted(
                ap.distribuicoes, key=lambda d: d.valor_centavos, reverse=True
            )
        ],
    )


@router.post("/{cliente_id}/apuracoes", response_model=ApuracaoOut)
async def criar_ou_atualizar_apuracao(
    cliente_id: UUID,
    body: ApuracaoIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApuracaoOut:
    """Cria (ou atualiza) a apuração de uma competência. Recalcula o resultado."""
    await verificar_acesso_cliente(db, user, cliente_id)

    result = await db.execute(
        select(ApuracaoSCP)
        .where(
            ApuracaoSCP.cliente_id == cliente_id,
            ApuracaoSCP.competencia == body.competencia,
        )
        .options(selectinload(ApuracaoSCP.distribuicoes))
    )
    ap = result.scalar_one_or_none()
    if ap is None:
        ap = ApuracaoSCP(cliente_id=cliente_id, competencia=body.competencia)
        db.add(ap)

    ap.receita_bruta_centavos = body.receita_bruta_centavos
    ap.custos_centavos = body.custos_centavos
    ap.resultado_centavos = max(
        body.receita_bruta_centavos - body.custos_centavos, 0
    )
    ap.observacoes = body.observacoes
    if ap.status == StatusApuracaoSCP.DISTRIBUIDA:
        ap.status = StatusApuracaoSCP.ABERTA  # alterou valores → reabre

    await db.commit()
    await db.refresh(ap)
    return _apuracao_para_out(ap)


@router.get("/apuracoes/{apuracao_id}", response_model=ApuracaoOut)
async def detalhe_apuracao(
    apuracao_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApuracaoOut:
    result = await db.execute(
        select(ApuracaoSCP)
        .where(ApuracaoSCP.id == apuracao_id)
        .options(selectinload(ApuracaoSCP.distribuicoes))
    )
    ap = result.scalar_one_or_none()
    if ap is None:
        raise HTTPException(status_code=404, detail="Apuração não encontrada")
    await verificar_acesso_cliente(db, user, ap.cliente_id)
    return _apuracao_para_out(ap)


@router.post("/apuracoes/{apuracao_id}/distribuir", response_model=ApuracaoOut)
async def distribuir_apuracao(
    apuracao_id: UUID,
    body: DistribuirIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApuracaoOut:
    """Calcula a distribuição do resultado entre os participantes da SCP."""
    result = await db.execute(
        select(ApuracaoSCP)
        .where(ApuracaoSCP.id == apuracao_id)
        .options(selectinload(ApuracaoSCP.distribuicoes))
    )
    ap = result.scalar_one_or_none()
    if ap is None:
        raise HTTPException(status_code=404, detail="Apuração não encontrada")
    await verificar_acesso_cliente(db, user, ap.cliente_id)

    # Converte chaves str->UUID das bases de serviço (ignora inválidas).
    bases: dict[UUID, int] = {}
    for k, v in body.bases_servico.items():
        try:
            bases[UUID(k)] = int(v)
        except (ValueError, TypeError):
            continue

    await gerar_distribuicao(db, ap, bases_servico=bases or None)
    ap.status = StatusApuracaoSCP.DISTRIBUIDA
    await db.commit()
    await db.refresh(ap)
    return _apuracao_para_out(ap)


__all__ = ["router"]
