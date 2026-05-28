"""Helpers de isolamento de tenant nas queries SQLAlchemy.

A função principal `aplicar_filtro_tenant` adiciona um `.where(Model.cliente_id == tenant_id)`
quando há um tenant ativo. Quando `tenant_id is None` (user MedPag
interno), retorna a query sem alteração — vê todos os tenants.

Padrão de uso:

    from app.core.tenant import aplicar_filtro_tenant
    from app.core.deps import get_tenant_id

    @router.get("/lotes")
    async def listar(
        tenant_id: UUID | None = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_db),
    ):
        stmt = select(Lote).where(Lote.status == StatusLote.RECEBIDO)
        stmt = aplicar_filtro_tenant(stmt, Lote, tenant_id)
        result = await db.execute(stmt)
        ...
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select


def aplicar_filtro_tenant(
    stmt: Select[Any], modelo: Any, tenant_id: UUID | None
) -> Select[Any]:
    """Adiciona filtro `modelo.cliente_id == tenant_id` se houver tenant.

    Args:
        stmt: query SQLAlchemy `select(...)` em construção
        modelo: classe do modelo (Lote, FichaPlantao, Beneficiario, etc).
            Precisa ter coluna `cliente_id`.
        tenant_id: UUID do cliente; None significa "sem filtro"
            (MedPag interno).

    Returns:
        Query com filtro aplicado (ou inalterada se tenant_id is None).
    """
    if tenant_id is None:
        return stmt
    return stmt.where(modelo.cliente_id == tenant_id)


__all__ = ["aplicar_filtro_tenant"]
