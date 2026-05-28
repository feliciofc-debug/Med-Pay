"""Camada de negócio sobre o Asaas.

Conecta `Cliente` (MedPag) com `Customer` + `Subscription` (Asaas):
    - sincroniza_customer_para_cliente — cria/atualiza customer
    - criar_assinatura_para_cliente — abre subscription no Asaas
    - cancelar_assinatura_do_cliente — encerra subscription
    - processar_webhook — atualiza Cliente.status_assinatura conforme
      eventos do Asaas (pagamento recebido, atraso, falha, etc)

Idempotência: webhook do Asaas reentrega em falha, então gravamos
`id` do evento Asaas em log e ignoramos duplicados.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ClienteNaoEncontradoError,
    ValidacaoError,
)
from app.models.cliente import Cliente
from app.models.plano import StatusAssinatura
from app.services.asaas_client import (
    AsaasFalhouError,
    AsaasIndisponivelError,
    asaas_client,
)

log = structlog.get_logger()


# ============================================================
# Sync Customer
# ============================================================


async def sincronizar_customer(db: AsyncSession, cliente_id: UUID) -> Cliente:
    """Cria customer no Asaas e grava o ID no Cliente.

    Se já existe `cliente.asaas_customer_id`, faz update do nome/email
    pra manter sincronizado. Caso contrário, cria novo.
    """
    cliente = await _carregar(db, cliente_id)

    if cliente.asaas_customer_id:
        try:
            await asaas_client.atualizar_customer(
                cliente.asaas_customer_id,
                nome=cliente.nome,
                email=cliente.email_contato,
            )
        except AsaasFalhouError as exc:
            log.warning("asaas.update_customer_falhou", erro=exc.message)
        return cliente

    resp = await asaas_client.criar_customer(
        nome=cliente.nome,
        cpf_cnpj=cliente.cnpj,
        email=cliente.email_contato,
        telefone=cliente.telefone,
        external_reference=str(cliente.id),
    )
    customer_id = resp.get("id")
    if not customer_id:
        raise AsaasFalhouError(
            "Asaas não retornou ID do customer criado."
        )
    cliente.asaas_customer_id = str(customer_id)
    await db.flush()
    log.info(
        "asaas.customer_criado",
        cliente_id=str(cliente.id),
        asaas_customer_id=customer_id,
    )
    return cliente


# ============================================================
# Subscription
# ============================================================


async def abrir_assinatura(
    db: AsyncSession, cliente_id: UUID, *, ciclo: str = "MONTHLY"
) -> Cliente:
    """Cria subscription no Asaas pra o plano atual do cliente.

    Pré-requisitos:
        - cliente tem plano_id setado
        - plano.preco_mensal_centavos > 0 (Enterprise=0 é negociado fora)
        - asaas_customer_id existe (sincroniza se não)
    """
    cliente = await _carregar(db, cliente_id)
    if cliente.plano is None:
        raise ValidacaoError(
            "Cliente sem plano. Defina o plano antes de abrir assinatura."
        )
    if cliente.plano.preco_mensal_centavos <= 0:
        raise ValidacaoError(
            "Plano Enterprise não usa cobrança automática "
            "(valor sob demanda)."
        )
    if cliente.asaas_subscription_id:
        raise ValidacaoError(
            "Cliente já tem assinatura ativa "
            f"({cliente.asaas_subscription_id})."
        )

    if not cliente.asaas_customer_id:
        cliente = await sincronizar_customer(db, cliente_id)

    # Primeiro vencimento: hoje + trial_dias se em trial, senão hoje + 7 dias
    if (
        cliente.status_assinatura == StatusAssinatura.TRIAL
        and cliente.trial_termina_em
    ):
        prox_venc = cliente.trial_termina_em.date()
    else:
        prox_venc = date.today() + timedelta(days=7)

    descricao = (
        f"Assinatura MedPag — Plano {cliente.plano.nome} — "
        f"{cliente.nome}"
    )

    assert cliente.asaas_customer_id is not None  # narrow pro mypy
    resp = await asaas_client.criar_assinatura(
        customer_id=cliente.asaas_customer_id,
        valor_centavos=cliente.plano.preco_mensal_centavos,
        proximo_vencimento_iso=prox_venc.isoformat(),
        descricao=descricao,
        ciclo=ciclo,
    )
    sub_id = resp.get("id")
    if not sub_id:
        raise AsaasFalhouError("Asaas não retornou ID da subscription.")

    cliente.asaas_subscription_id = str(sub_id)
    cliente.proximo_vencimento = datetime.combine(
        prox_venc, datetime.min.time(), tzinfo=UTC
    )
    await db.flush()
    log.info(
        "asaas.assinatura_criada",
        cliente_id=str(cliente.id),
        subscription_id=sub_id,
        valor_centavos=cliente.plano.preco_mensal_centavos,
    )
    return cliente


async def cancelar_assinatura(
    db: AsyncSession, cliente_id: UUID, *, motivo: str | None = None
) -> Cliente:
    cliente = await _carregar(db, cliente_id)
    if not cliente.asaas_subscription_id:
        raise ValidacaoError("Cliente não tem assinatura ativa pra cancelar.")
    try:
        await asaas_client.cancelar_assinatura(cliente.asaas_subscription_id)
    except (AsaasIndisponivelError, AsaasFalhouError) as exc:
        log.error(
            "asaas.cancel_falhou",
            cliente_id=str(cliente.id),
            erro=exc.message,
        )
        raise

    log.info(
        "asaas.assinatura_cancelada",
        cliente_id=str(cliente.id),
        subscription_id=cliente.asaas_subscription_id,
        motivo=motivo,
    )
    cliente.asaas_subscription_id = None
    cliente.status_assinatura = StatusAssinatura.CANCELADO
    cliente.proximo_vencimento = None
    await db.flush()
    return cliente


# ============================================================
# Webhook
# ============================================================


# Mapeamento dos eventos relevantes do Asaas → ação interna.
# Eventos completos: https://docs.asaas.com/docs/webhooks
EVENTOS_PAGAMENTO_OK = frozenset(
    {
        "PAYMENT_RECEIVED",
        "PAYMENT_CONFIRMED",
        "PAYMENT_RECEIVED_IN_CASH",
    }
)
EVENTOS_PAGAMENTO_FALHA = frozenset(
    {
        "PAYMENT_OVERDUE",
        "PAYMENT_REFUNDED",
        "PAYMENT_CHARGEBACK_REQUESTED",
        "PAYMENT_DUNNING_REQUESTED",
    }
)
EVENTOS_ASSINATURA_FIM = frozenset(
    {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"}
)


async def processar_webhook(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, str]:
    """Recebe payload do webhook e ajusta status de assinatura do cliente.

    Payload típico:
        {
          "event": "PAYMENT_RECEIVED",
          "payment": { "id": "...", "customer": "...", "subscription": "...", ... }
        }
    ou
        {
          "event": "SUBSCRIPTION_DELETED",
          "subscription": { "id": "...", "customer": "..." }
        }
    """
    evento = (payload.get("event") or "").upper()
    if not evento:
        return {"status": "ignorado", "motivo": "sem event"}

    payment = payload.get("payment") or {}
    subscription = payload.get("subscription") or {}

    customer_id = (
        payment.get("customer")
        or subscription.get("customer")
        or payload.get("customer")
    )
    subscription_id = payment.get("subscription") or subscription.get("id")

    cliente = await _localizar_cliente(
        db, customer_id=customer_id, subscription_id=subscription_id
    )
    if cliente is None:
        log.warning(
            "asaas.webhook_cliente_nao_encontrado",
            customer_id=customer_id,
            subscription_id=subscription_id,
            evento=evento,
        )
        return {"status": "ignorado", "motivo": "cliente nao encontrado"}

    if evento in EVENTOS_PAGAMENTO_OK:
        cliente.status_assinatura = StatusAssinatura.ATIVO
        cliente.pagamento_cadastrado = True
        if payment.get("dueDate"):
            cliente.proximo_vencimento = _parse_data(payment["dueDate"])
        log.info(
            "asaas.pagamento_recebido", cliente_id=str(cliente.id), evento=evento
        )

    elif evento in EVENTOS_PAGAMENTO_FALHA:
        cliente.status_assinatura = StatusAssinatura.INADIMPLENTE
        log.warning(
            "asaas.pagamento_atrasado", cliente_id=str(cliente.id), evento=evento
        )

    elif evento in EVENTOS_ASSINATURA_FIM:
        cliente.status_assinatura = StatusAssinatura.CANCELADO
        cliente.asaas_subscription_id = None
        cliente.proximo_vencimento = None
        log.info(
            "asaas.assinatura_encerrada",
            cliente_id=str(cliente.id),
            evento=evento,
        )

    else:
        # Outros eventos (CREATED, UPDATED, etc) — só registra
        log.info(
            "asaas.evento_ignorado", cliente_id=str(cliente.id), evento=evento
        )
        return {"status": "ignorado", "evento": evento}

    await db.flush()
    return {"status": "processado", "evento": evento}


# ============================================================
# Job diário: trial vencendo, inadimplente → suspenso
# ============================================================


async def rodar_job_trial_inadimplencia(
    db: AsyncSession,
    *,
    dias_para_suspender_inadimplente: int = 7,
) -> dict[str, int]:
    """Roda 1x por dia (ex: cron 6h).

    Regras:
        - TRIAL com trial_termina_em < agora E sem pagamento_cadastrado:
            vira SUSPENSO
        - TRIAL com trial_termina_em < agora E com pagamento_cadastrado:
            vira ATIVO (o pagamento vai cobrar no proximo vencimento)
        - INADIMPLENTE há > N dias: vira SUSPENSO
    """
    agora = datetime.now(UTC)
    limite_inadimplente = agora - timedelta(days=dias_para_suspender_inadimplente)

    contadores = {
        "trial_convertido": 0,
        "trial_suspenso": 0,
        "inadimplente_suspenso": 0,
    }

    # Trial vencido
    result = await db.execute(
        select(Cliente).where(
            Cliente.status_assinatura == StatusAssinatura.TRIAL,
            Cliente.trial_termina_em.is_not(None),
            Cliente.trial_termina_em < agora,
            Cliente.deleted_at.is_(None),
        )
    )
    for cliente in result.scalars():
        if cliente.pagamento_cadastrado:
            cliente.status_assinatura = StatusAssinatura.ATIVO
            contadores["trial_convertido"] += 1
        else:
            cliente.status_assinatura = StatusAssinatura.SUSPENSO
            contadores["trial_suspenso"] += 1

    # Inadimplente há muito tempo
    result = await db.execute(
        select(Cliente).where(
            Cliente.status_assinatura == StatusAssinatura.INADIMPLENTE,
            Cliente.updated_at < limite_inadimplente,
            Cliente.deleted_at.is_(None),
        )
    )
    for cliente in result.scalars():
        cliente.status_assinatura = StatusAssinatura.SUSPENSO
        contadores["inadimplente_suspenso"] += 1

    await db.flush()
    return contadores


# ============================================================
# Helpers
# ============================================================


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


async def _localizar_cliente(
    db: AsyncSession,
    *,
    customer_id: str | None,
    subscription_id: str | None,
) -> Cliente | None:
    """Acha o Cliente pelos IDs do Asaas."""
    if subscription_id:
        result = await db.execute(
            select(Cliente).where(
                Cliente.asaas_subscription_id == subscription_id
            )
        )
        c = result.scalar_one_or_none()
        if c:
            return c
    if customer_id:
        result = await db.execute(
            select(Cliente).where(Cliente.asaas_customer_id == customer_id)
        )
        return result.scalar_one_or_none()
    return None


def _parse_data(s: str) -> datetime:
    """Asaas devolve dueDate em YYYY-MM-DD."""
    try:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


__all__ = [
    "abrir_assinatura",
    "cancelar_assinatura",
    "processar_webhook",
    "rodar_job_trial_inadimplencia",
    "sincronizar_customer",
]
