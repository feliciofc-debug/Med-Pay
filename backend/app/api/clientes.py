"""Rotas de gerenciamento de clientes (hospitais, clínicas, ONGs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_admin
from app.models.cliente import Cliente
from app.models.user import User

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def listar_clientes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[dict[str, object]]]:
    """Lista todos os clientes ativos."""
    result = await db.execute(
        select(Cliente).where(Cliente.deleted_at.is_(None)).order_by(Cliente.nome)
    )
    clientes = result.scalars().all()
    return {
        "clientes": [
            {
                "id": str(c.id),
                "nome": c.nome,
                "cnpj": c.cnpj,
                "email_contato": c.email_contato,
                "ativo": c.ativo,
            }
            for c in clientes
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_cliente(
    payload: dict[str, object],
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, object]:
    """Cria um novo cliente (apenas ADMIN).

    TODO: criar schema Pydantic ClienteCreate quando a feature for fechada.
    """
    nome = str(payload.get("nome", "")).strip()
    if not nome:
        from app.core.exceptions import ValidacaoError

        raise ValidacaoError("Nome do cliente é obrigatório")

    cliente = Cliente(
        nome=nome,
        cnpj=payload.get("cnpj") or None,  # type: ignore[arg-type]
        email_contato=payload.get("email_contato") or None,  # type: ignore[arg-type]
        telefone=payload.get("telefone") or None,  # type: ignore[arg-type]
        email_remetente_autorizado=payload.get("email_remetente_autorizado") or None,  # type: ignore[arg-type]
    )
    db.add(cliente)
    await db.flush()
    return {"id": str(cliente.id), "nome": cliente.nome}
