"""Configuração operacional por cliente.

GET  /api/operacao/{cliente_id}  → config atual
PUT  /api/operacao/{cliente_id}  → atualiza (PATCH semântico — só campos enviados)

Acesso: ADMIN. Quando migrarmos pra multi-tenant (User.cliente_id),
verificamos `user.cliente_id == cliente_id` aqui.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, verificar_acesso_cliente
from app.core.exceptions import ClienteNaoEncontradoError
from app.models.cliente import Cliente
from app.models.user import User
from app.schemas.operacao import (
    AtualizarConfigOperacaoRequest,
    ConfigOperacaoOut,
)

router = APIRouter()


async def _carregar(db: AsyncSession, cliente_id: UUID) -> Cliente:
    result = await db.execute(
        select(Cliente).where(
            Cliente.id == cliente_id, Cliente.deleted_at.is_(None)
        )
    )
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise ClienteNaoEncontradoError(f"Cliente {cliente_id} não encontrado")
    return cliente


@router.get("/{cliente_id}", response_model=ConfigOperacaoOut)
async def obter_config(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ConfigOperacaoOut:
    verificar_acesso_cliente(admin, cliente_id)
    cliente = await _carregar(db, cliente_id)
    return ConfigOperacaoOut.model_validate(cliente)


@router.put("/{cliente_id}", response_model=ConfigOperacaoOut)
async def atualizar_config(
    cliente_id: UUID,
    payload: AtualizarConfigOperacaoRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ConfigOperacaoOut:
    verificar_acesso_cliente(admin, cliente_id)
    cliente = await _carregar(db, cliente_id)
    if payload.dia_fechamento is not None:
        cliente.dia_fechamento = payload.dia_fechamento
    if payload.fuso_horario is not None:
        cliente.fuso_horario = payload.fuso_horario
    if payload.modalidade_preferida is not None:
        cliente.modalidade_preferida = payload.modalidade_preferida
    if payload.logo_url is not None:
        cliente.logo_url = payload.logo_url or None
    if payload.cor_primaria is not None:
        cliente.cor_primaria = payload.cor_primaria
    await db.flush()
    return ConfigOperacaoOut.model_validate(cliente)
