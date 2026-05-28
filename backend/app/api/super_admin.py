"""Rotas do Painel Super Admin.

Visão "do dono da MedPag" — agrega tudo: MRR, ARR, churn, distribuição
por plano, health score por cliente. Restrito a `require_admin`.

Quando criarmos role separada `SUPER_ADMIN` (sócio MedPag vs admin de
um cliente), trocamos a dependência. Por enquanto ADMIN = sócio MedPag.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.super_admin import ClienteOverviewOut, MetricasSaaSOut
from app.services.super_admin_service import (
    calcular_metricas,
    listar_clientes_overview,
)

router = APIRouter()


@router.get("/metricas", response_model=MetricasSaaSOut)
async def metricas_saas(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MetricasSaaSOut:
    """Snapshot de MRR/ARR/ARPU + distribuição por plano + funil."""
    metricas = await calcular_metricas(db)
    return MetricasSaaSOut(**asdict(metricas))


@router.get("/clientes", response_model=list[ClienteOverviewOut])
async def overview_clientes(
    limite: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[ClienteOverviewOut]:
    """Tabela detalhada por cliente com health score + sinais."""
    overview = await listar_clientes_overview(db, limite=limite)
    return [ClienteOverviewOut(**asdict(c)) for c in overview]
