"""Resolução da conta pagadora ("Conta de Repasse") usada num pagamento.

Com a carteira de repasse, um tenant tem N contas (uma por banco) e cada
hospital aponta pra uma. Este módulo centraliza a regra de "qual conta
usar", com fallback pro comportamento single-tenant legado — assim o CNAB
que já roda não quebra.

Ordem de resolução (do mais específico pro mais genérico):
    1. `Cliente.conta_pagadora_id` — vínculo explícito do hospital.
    2. Uma conta ativa cujo `cliente_id` == o do cliente (própria do tenant).
    3. Conta legada/global (`cliente_id IS NULL`, ativa) — compat antigo.
    4. Qualquer conta ativa (último recurso).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cliente import Cliente
from app.models.empresa_config import EmpresaConfig
from app.models.lote import Lote


async def resolver_conta_do_cliente(
    db: AsyncSession, cliente_id: UUID | None
) -> EmpresaConfig | None:
    """Resolve a conta pagadora de um cliente (hospital), com fallback."""
    # 1. vínculo explícito do cliente
    if cliente_id is not None:
        cliente = await db.get(Cliente, cliente_id)
        if cliente is not None and cliente.conta_pagadora_id is not None:
            conta = await db.get(EmpresaConfig, cliente.conta_pagadora_id)
            if conta is not None and conta.ativo:
                return conta

        # 2. conta própria do tenant
        q = await db.execute(
            select(EmpresaConfig)
            .where(
                EmpresaConfig.cliente_id == cliente_id,
                EmpresaConfig.ativo.is_(True),
            )
            .limit(1)
        )
        conta = q.scalar_one_or_none()
        if conta is not None:
            return conta

    # 3. conta legada/global (single-tenant antigo)
    q = await db.execute(
        select(EmpresaConfig)
        .where(EmpresaConfig.cliente_id.is_(None), EmpresaConfig.ativo.is_(True))
        .limit(1)
    )
    conta = q.scalar_one_or_none()
    if conta is not None:
        return conta

    # 4. último recurso: qualquer conta ativa
    q = await db.execute(
        select(EmpresaConfig).where(EmpresaConfig.ativo.is_(True)).limit(1)
    )
    return q.scalar_one_or_none()


async def resolver_conta_pagadora_lote(
    db: AsyncSession, lote: Lote
) -> EmpresaConfig | None:
    """Resolve a conta pagadora que executa um lote (pelo cliente do lote)."""
    return await resolver_conta_do_cliente(db, lote.cliente_id)


__all__ = ["resolver_conta_do_cliente", "resolver_conta_pagadora_lote"]
