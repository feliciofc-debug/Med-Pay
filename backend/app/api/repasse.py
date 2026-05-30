"""Rotas de execução de repasse: export RH e validação de PIX.

    GET  /api/repasse/lotes/{lote_id}/export-rh  → baixa CSV pro RH
    POST /api/repasse/validar-pix                → confere titularidade PIX↔CPF

O repasse via CNAB continua no fluxo de lotes existente; aqui ficam os
modos alternativos (EXPORT_RH) e o antifraude da cadeia de confiança.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, verificar_acesso_cliente
from app.models.lote import Lote
from app.models.pagamento import StatusPagamento
from app.models.user import User
from app.services.export_rh import gerar_export_rh_csv, nome_arquivo_export
from app.services.pix_validacao import ResultadoPix, validar_titularidade_pix

log = structlog.get_logger()
router = APIRouter()

# Status que entram no export (os que serão/foram pagos).
_STATUS_EXPORTAVEIS = {
    StatusPagamento.VALIDO,
    StatusPagamento.CORRIGIVEL,
    StatusPagamento.APROVADO,
    StatusPagamento.PAGO,
}


@router.get("/lotes/{lote_id}/export-rh")
async def exportar_rh(
    lote_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera e baixa o CSV do lote pro RH do cliente processar a folha."""
    result = await db.execute(
        select(Lote)
        .where(Lote.id == lote_id)
        .options(selectinload(Lote.pagamentos))
    )
    lote = result.scalar_one_or_none()
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    verificar_acesso_cliente(user, lote.cliente_id)

    pagamentos = [
        p for p in lote.pagamentos if p.status in _STATUS_EXPORTAVEIS
    ]
    competencia = lote.referencia or ""
    conteudo = gerar_export_rh_csv(competencia=competencia, pagamentos=pagamentos)
    nome = nome_arquivo_export(lote)

    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


class ValidarPixIn(BaseModel):
    chave_pix: str = Field(min_length=1, description="Chave PIX a verificar")
    cpf: str = Field(min_length=1, description="CPF esperado (do médico)")
    cnpjs_vinculados: list[str] = Field(
        default_factory=list,
        description="CNPJs de clínicas vinculadas ao médico (aceitos como PJ).",
    )


class ValidarPixOut(BaseModel):
    resultado: ResultadoPix
    mensagem: str
    nome_titular: str | None = None
    doc_titular: str | None = None


@router.post("/validar-pix", response_model=ValidarPixOut)
async def validar_pix(
    body: ValidarPixIn,
    _: User = Depends(get_current_user),
) -> ValidarPixOut:
    """Confere se a chave PIX pertence ao CPF (ou CNPJ vinculado) do médico."""
    veredicto = await validar_titularidade_pix(
        chave_pix=body.chave_pix,
        cpf_esperado=body.cpf,
        cnpjs_vinculados=body.cnpjs_vinculados,
    )
    return ValidarPixOut(
        resultado=veredicto.resultado,
        mensagem=veredicto.mensagem,
        nome_titular=veredicto.nome_titular,
        doc_titular=veredicto.doc_titular,
    )


__all__ = ["router"]
