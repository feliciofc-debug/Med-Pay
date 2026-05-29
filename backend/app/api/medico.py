"""API do app do medico (prestador).

Endpoints exclusivos pra usuarios com role MEDICO. Todos protegidos
por require_medico (recusa qualquer outro papel exceto ADMIN, que
pode entrar pra suporte).

Endpoints:
    GET /api/medico/me        → perfil + vinculo
    GET /api/medico/plantoes  → lista de plantoes lancados em fichas
    GET /api/medico/extrato   → pagamentos + totalizadores
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_medico
from app.models.user import User
from app.services import medico_app_service

router = APIRouter()


# ============================================================
# Pydantic schemas
# ============================================================


class PerfilMedicoOut(BaseModel):
    nome: str
    email: str
    cpf_mascarado: str | None
    hospital: str | None
    hospital_id: str | None
    beneficiario_id: str | None
    vinculado: bool
    pix_modalidade: str | None
    pix_chave_mascarada: str | None
    banco_nome: str | None
    conta_mascarada: str | None
    conta_verificada: bool


class PlantaoOut(BaseModel):
    ficha_id: str
    nome_arquivo: str
    competencia: str | None
    coordenador: str | None
    data_lancamento: datetime
    status_ficha: str
    valor_centavos: int
    detalhe: str | None


class PagamentoOut(BaseModel):
    pagamento_id: str
    lote_id: str
    valor_centavos: int
    status: str
    status_label: str
    modalidade: str
    criado_em: datetime
    pago_em: datetime | None
    motivo_rejeicao: str | None


class ResumoExtratoOut(BaseModel):
    total_pago_centavos: int
    total_pendente_centavos: int
    total_rejeitado_centavos: int
    qtd_pagamentos: int


class ExtratoResponse(BaseModel):
    resumo: ResumoExtratoOut
    pagamentos: list[PagamentoOut]


class PlantoesResponse(BaseModel):
    plantoes: list[PlantaoOut]
    total: int
    valor_total_centavos: int


# ============================================================
# Endpoints
# ============================================================


@router.get("/me", response_model=PerfilMedicoOut)
async def me(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_medico),
) -> PerfilMedicoOut:
    """Perfil do prestador logado (com vinculo ao cadastro de Beneficiario)."""
    perfil = await medico_app_service.obter_perfil(db, user)
    return PerfilMedicoOut(
        nome=perfil.nome,
        email=perfil.email,
        cpf_mascarado=perfil.cpf_mascarado,
        hospital=perfil.hospital,
        hospital_id=perfil.hospital_id,
        beneficiario_id=perfil.beneficiario_id,
        vinculado=perfil.vinculado,
        pix_modalidade=perfil.pix_modalidade,
        pix_chave_mascarada=perfil.pix_chave_mascarada,
        banco_nome=perfil.banco_nome,
        conta_mascarada=perfil.conta_mascarada,
        conta_verificada=perfil.conta_verificada,
    )


@router.get("/plantoes", response_model=PlantoesResponse)
async def listar_plantoes(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_medico),
) -> PlantoesResponse:
    """Lista os plantoes onde o medico aparece (via CPF nas fichas)."""
    plantoes = await medico_app_service.listar_plantoes(db, user, limit=limit)
    total_valor = sum(p.valor_centavos for p in plantoes)
    return PlantoesResponse(
        plantoes=[
            PlantaoOut(
                ficha_id=p.ficha_id,
                nome_arquivo=p.nome_arquivo,
                competencia=p.competencia,
                coordenador=p.coordenador,
                data_lancamento=p.data_lancamento,
                status_ficha=p.status_ficha,
                valor_centavos=p.valor_centavos,
                detalhe=p.detalhe,
            )
            for p in plantoes
        ],
        total=len(plantoes),
        valor_total_centavos=total_valor,
    )


@router.get("/extrato", response_model=ExtratoResponse)
async def extrato(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_medico),
) -> ExtratoResponse:
    """Extrato de pagamentos + resumo (pago / pendente / rejeitado)."""
    pagamentos, resumo = await medico_app_service.listar_pagamentos(
        db, user, limit=limit
    )
    return ExtratoResponse(
        resumo=ResumoExtratoOut(
            total_pago_centavos=resumo.total_pago_centavos,
            total_pendente_centavos=resumo.total_pendente_centavos,
            total_rejeitado_centavos=resumo.total_rejeitado_centavos,
            qtd_pagamentos=resumo.qtd_pagamentos,
        ),
        pagamentos=[
            PagamentoOut(
                pagamento_id=p.pagamento_id,
                lote_id=p.lote_id,
                valor_centavos=p.valor_centavos,
                status=p.status,
                status_label=p.status_label,
                modalidade=p.modalidade,
                criado_em=p.criado_em,
                pago_em=p.pago_em,
                motivo_rejeicao=p.motivo_rejeicao,
            )
            for p in pagamentos
        ],
    )
