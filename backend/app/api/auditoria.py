"""Visualização do log de auditoria.

Lista append-only de operações sensíveis. Sem write — só leitura
filtrável + paginada. Restrito a ADMIN.

Filtros:
    - acao (ex: LOTE_APROVADO, CNAB_GERADO, LOGIN)
    - entidade_tipo (Lote, Pagamento, Cliente, User)
    - user_id (quem fez)
    - desde / ate (range de datas)
    - busca livre na mensagem
"""

from __future__ import annotations

from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.deps import get_db, require_admin
from app.models.auditoria import Auditoria
from app.models.user import User
from app.schemas.auditoria import AuditoriaOut, AuditoriaPage

router = APIRouter()


def _auditoria_para_out(a: Auditoria) -> AuditoriaOut:
    return AuditoriaOut(
        id=a.id,
        user_id=a.user_id,
        user_nome=a.user.nome if a.user else None,
        user_email=a.user.email if a.user else None,
        acao=a.acao,
        entidade_tipo=a.entidade_tipo,
        entidade_id=a.entidade_id,
        detalhes=a.detalhes,
        hash_relacionado=a.hash_relacionado,
        ip_address=str(a.ip_address) if a.ip_address else None,
        mensagem=a.mensagem,
        created_at=a.created_at,
    )


@router.get("", response_model=AuditoriaPage)
async def listar_auditoria(
    acao: str | None = Query(None, description="Filtra por ação exata"),
    entidade_tipo: str | None = Query(None),
    user_id: UUID | None = Query(None),
    desde: datetime | None = Query(None, description="ISO 8601"),
    ate: datetime | None = Query(None, description="ISO 8601"),
    busca: str | None = Query(None, description="Busca livre em mensagem/ação"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AuditoriaPage:
    filtros = []
    if acao:
        filtros.append(Auditoria.acao == acao)
    if entidade_tipo:
        filtros.append(Auditoria.entidade_tipo == entidade_tipo)
    if user_id is not None:
        filtros.append(Auditoria.user_id == user_id)
    if desde:
        filtros.append(Auditoria.created_at >= desde)
    if ate:
        filtros.append(Auditoria.created_at <= ate)
    if busca:
        term = f"%{busca.lower()}%"
        filtros.append(
            or_(
                func.lower(Auditoria.acao).like(term),
                func.lower(Auditoria.mensagem).like(term),
            )
        )

    where_clause = and_(*filtros) if filtros else None

    # Total
    count_q = select(func.count(Auditoria.id))
    if where_clause is not None:
        count_q = count_q.where(where_clause)
    total_res = await db.execute(count_q)
    total = int(total_res.scalar() or 0)

    # Página
    offset = (page - 1) * per_page
    list_q = (
        select(Auditoria)
        .options(joinedload(Auditoria.user))
        .order_by(Auditoria.created_at.desc())
        .limit(per_page)
        .offset(offset)
    )
    if where_clause is not None:
        list_q = list_q.where(where_clause)

    result = await db.execute(list_q)
    itens = [_auditoria_para_out(a) for a in result.scalars().all()]

    return AuditoriaPage(
        items=itens,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, ceil(total / per_page)),
    )


@router.get("/acoes", response_model=list[str])
async def listar_acoes_disponiveis(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[str]:
    """Lista distinct de ações já registradas — pro filtro do frontend."""
    result = await db.execute(
        select(Auditoria.acao).distinct().order_by(Auditoria.acao)
    )
    return [row[0] for row in result.all() if row[0]]
