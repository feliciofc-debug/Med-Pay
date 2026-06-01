"""Endpoints da integração Asaas.

Público:
    POST /api/asaas/webhook                 → Asaas → MedPag (atualiza status)

Admin:
    GET  /api/asaas/status                  → diagnostica config
    POST /api/asaas/clientes/{id}/customer  → cria/atualiza customer
    POST /api/asaas/clientes/{id}/subscription → cria subscription
    DEL  /api/asaas/clientes/{id}/subscription → cancela
    POST /api/asaas/job/diario              → roda job manualmente (cron faz sozinho em prod)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_admin
from app.models.user import User
from app.services.asaas_client import asaas_client
from app.services.asaas_service import (
    abrir_assinatura,
    cancelar_assinatura,
    processar_webhook,
    rodar_job_trial_inadimplencia,
    sincronizar_customer,
)
from app.services.pix_validacao import ResultadoPix, validar_titularidade_pix

log = structlog.get_logger()
router = APIRouter()


# ============================================================
# Status / Diagnóstico
# ============================================================


@router.get("/status")
async def status_integracao(
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Conta se o Asaas está configurado e qual ambiente."""
    return {
        "configurado": asaas_client.is_configured(),
        "base_url": settings.ASAAS_BASE_URL,
        "billing_type_padrao": settings.ASAAS_DEFAULT_BILLING_TYPE,
        "webhook_token_configurado": bool(settings.ASAAS_WEBHOOK_TOKEN),
    }


# ============================================================
# Validação de conta/chave PIX (antifraude do repasse)
# ============================================================


class ValidarContaRequest(BaseModel):
    """Pede pra confirmar que a chave PIX pertence ao CPF do médico."""

    chave_pix: str = Field(
        ...,
        min_length=3,
        description="Chave PIX (CPF/CNPJ/e-mail/telefone/aleatória) ou copia-e-cola.",
    )
    cpf_esperado: str = Field(
        ..., description="CPF do médico que deveria ser o dono da chave."
    )
    cnpjs_vinculados: list[str] = Field(
        default_factory=list,
        description="CNPJs de clínicas/PJ vinculadas ao médico (libera recebimento por PJ).",
    )


class ValidarContaResponse(BaseModel):
    resultado: ResultadoPix
    mensagem: str
    nome_titular: str | None = None
    doc_titular: str | None = None
    asaas_configurado: bool


@router.post("/validar-conta", response_model=ValidarContaResponse)
async def validar_conta(
    payload: ValidarContaRequest,
    _user: User = Depends(get_current_user),
) -> ValidarContaResponse:
    """Consulta a titularidade da chave PIX no Asaas e cruza com o CPF do médico.

    Vereditos:
        - CONFERE     → a chave é do CPF do médico (ou de PJ vinculada)
        - DIVERGENTE  → a chave é de outra pessoa (risco de fraude)
        - PENDENTE    → não deu pra verificar agora (Asaas sem chave/indisponível)

    Não move dinheiro: é só consulta. Enquanto a chave do Asaas não estiver
    configurada, devolve PENDENTE (operador revisa manual).
    """
    veredicto = await validar_titularidade_pix(
        chave_pix=payload.chave_pix,
        cpf_esperado=payload.cpf_esperado,
        cnpjs_vinculados=payload.cnpjs_vinculados,
    )
    return ValidarContaResponse(
        resultado=veredicto.resultado,
        mensagem=veredicto.mensagem,
        nome_titular=veredicto.nome_titular,
        doc_titular=veredicto.doc_titular,
        asaas_configurado=asaas_client.is_configured(),
    )


# ============================================================
# Customer + Subscription (admin)
# ============================================================


@router.post("/clientes/{cliente_id}/customer")
async def sincronizar_customer_cliente(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, str]:
    cliente = await sincronizar_customer(db, cliente_id)
    return {
        "cliente_id": str(cliente.id),
        "asaas_customer_id": cliente.asaas_customer_id or "",
    }


@router.post("/clientes/{cliente_id}/subscription")
async def abrir_subscription(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, str | None]:
    cliente = await abrir_assinatura(db, cliente_id)
    return {
        "cliente_id": str(cliente.id),
        "asaas_subscription_id": cliente.asaas_subscription_id,
        "proximo_vencimento": (
            cliente.proximo_vencimento.isoformat()
            if cliente.proximo_vencimento
            else None
        ),
    }


@router.delete("/clientes/{cliente_id}/subscription")
async def encerrar_subscription(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, str]:
    cliente = await cancelar_assinatura(db, cliente_id)
    return {"cliente_id": str(cliente.id), "status": "cancelada"}


# ============================================================
# Job diário (cron)
# ============================================================


@router.post("/job/diario")
async def disparar_job_diario(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, int]:
    """Pra rodar manualmente em ambiente sem cron.

    Em produção, recomendamos cron diário via Render Cron Job:
        curl -X POST -H "Authorization: Bearer <token>" \\
             https://medpag-api.onrender.com/api/asaas/job/diario
    """
    return await rodar_job_trial_inadimplencia(db)


# ============================================================
# Webhook (público — Asaas chama aqui)
# ============================================================


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook_asaas(
    request: Request,
    db: AsyncSession = Depends(get_db),
    asaas_access_token: str | None = Header(None, alias="asaas-access-token"),
) -> dict[str, str]:
    """Endpoint que o Asaas chama em cada evento.

    Sempre devolve 200 (mesmo em erro), porque o Asaas faz retry agressivo
    e a gente quer evitar fila acumulando. Erros são logados pra
    investigação manual.
    """
    if settings.ASAAS_WEBHOOK_TOKEN:
        if asaas_access_token != settings.ASAAS_WEBHOOK_TOKEN:
            log.warning(
                "asaas.webhook_token_invalido",
                ip=request.client.host if request.client else None,
            )
            return {"status": "ignorado", "motivo": "token_invalido"}

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("asaas.webhook_payload_invalido", erro=str(exc))
        return {"status": "ignorado", "motivo": "payload_invalido"}

    try:
        return await processar_webhook(db, payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("asaas.webhook_erro")
        return {"status": "erro", "motivo": str(exc)[:200]}
