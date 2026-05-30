"""Rotas de metadados da engenharia de modelos de negócio.

Expõe pro frontend/admin os presets de tipo de tenant e as estratégias
de repasse — pra telas de criação/edição de cliente montarem os selects
sem hardcode.

    GET /api/modelos-negocio/presets       → presets por tipo de tenant
    GET /api/modelos-negocio/estrategias    → estratégias de repasse
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.cliente import ModoPagamento, TipoCliente
from app.models.user import User
from app.services.presets_negocio import PRESETS
from app.services.repasse_dispatcher import todas_estrategias

router = APIRouter()


class PresetOut(BaseModel):
    tipo: TipoCliente
    nome: str
    descricao: str
    modo_pagamento: ModoPagamento
    features: dict[str, object]


class EstrategiaOut(BaseModel):
    modo: ModoPagamento
    label: str
    descricao: str
    gera_arquivo: bool
    formato: str | None
    executa_pagamento: bool


@router.get("/presets", response_model=list[PresetOut])
async def listar_presets(
    _: User = Depends(get_current_user),
) -> list[PresetOut]:
    """Presets dos modelos de negócio (tipo → modo + features padrão)."""
    return [
        PresetOut(
            tipo=p.tipo,
            nome=p.nome,
            descricao=p.descricao,
            modo_pagamento=p.modo_pagamento,
            features=dict(p.features),
        )
        for p in PRESETS.values()
    ]


@router.get("/estrategias", response_model=list[EstrategiaOut])
async def listar_estrategias(
    _: User = Depends(get_current_user),
) -> list[EstrategiaOut]:
    """Estratégias de repasse disponíveis (Eixo 3)."""
    return [
        EstrategiaOut(
            modo=e.modo,
            label=e.label,
            descricao=e.descricao,
            gera_arquivo=e.gera_arquivo,
            formato=e.formato,
            executa_pagamento=e.executa_pagamento,
        )
        for e in todas_estrategias()
    ]


__all__ = ["router"]
