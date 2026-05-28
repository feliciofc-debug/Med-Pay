"""Onboarding self-service.

Cria Cliente + User admin do cliente + (opcional) customer Asaas
numa transação só. Plano vem do `slug` selecionado no wizard
(`/api/planos/publicos`). Se o plano tiver `trial_dias > 0`,
inicia em TRIAL com data de fim setada.

Validação:
    - Email único na tabela users
    - CNPJ único na tabela clientes (se informado)
    - Plano deve estar publico=True e ativo=True

Retorna o User criado + tokens, pra logar direto após signup.

Asaas é best-effort: se ASAAS_API_KEY não estiver setada, signup
funciona normalmente e o cliente nasce sem `asaas_customer_id` —
o admin pode sincronizar depois via /api/asaas/clientes/.../customer.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    PlanoNaoEncontradoError,
    UsuarioJaExisteError,
    ValidacaoError,
)
from app.core.security import hash_password
from app.models.cliente import Cliente
from app.models.plano import Plano, StatusAssinatura
from app.models.user import User, UserRole
from app.services.asaas_client import (
    AsaasFalhouError,
    AsaasIndisponivelError,
    asaas_client,
)

log = structlog.get_logger()


def _normalizar_cnpj(s: str | None) -> str | None:
    if not s:
        return None
    cnpj = re.sub(r"\D", "", s)
    if len(cnpj) != 14:
        raise ValidacaoError("CNPJ deve ter 14 dígitos.")
    return cnpj


def _normalizar_email(s: str) -> str:
    e = s.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        raise ValidacaoError("E-mail inválido.")
    return e


async def signup(
    db: AsyncSession,
    *,
    plano_slug: str,
    nome_empresa: str,
    cnpj: str | None,
    email_contato: str | None,
    telefone: str | None,
    admin_nome: str,
    admin_email: str,
    admin_senha: str,
) -> tuple[Cliente, User]:
    """Cria cliente + user admin + (best-effort) customer Asaas.

    Retorna `(cliente, user)`. O caller monta a resposta (tokens, etc).
    """
    if len(admin_senha) < 8:
        raise ValidacaoError("Senha precisa ter pelo menos 8 caracteres.")

    admin_email_norm = _normalizar_email(admin_email)
    contato_norm = _normalizar_email(email_contato) if email_contato else None
    cnpj_norm = _normalizar_cnpj(cnpj)
    nome_empresa = nome_empresa.strip()
    if not nome_empresa:
        raise ValidacaoError("Nome da empresa obrigatório.")

    # Plano
    plano_q = await db.execute(
        select(Plano).where(
            Plano.slug == plano_slug,
            Plano.ativo.is_(True),
            Plano.publico.is_(True),
        )
    )
    plano = plano_q.scalar_one_or_none()
    if plano is None:
        raise PlanoNaoEncontradoError(
            f"Plano '{plano_slug}' indisponível pra signup self-service. "
            "Planos contratuais só podem ser atribuídos pelo admin."
        )

    # Email único
    user_existe_q = await db.execute(
        select(User.id).where(User.email == admin_email_norm)
    )
    if user_existe_q.scalar_one_or_none():
        raise UsuarioJaExisteError(
            f"Já existe usuário com email {admin_email_norm}."
        )

    # CNPJ único
    if cnpj_norm:
        cnpj_existe_q = await db.execute(
            select(Cliente.id).where(Cliente.cnpj == cnpj_norm)
        )
        if cnpj_existe_q.scalar_one_or_none():
            raise ValidacaoError(
                f"Já existe cliente com CNPJ {cnpj_norm}."
            )

    agora = datetime.now(UTC)
    trial_termina_em = (
        agora + timedelta(days=plano.trial_dias)
        if plano.trial_dias > 0
        else None
    )
    status = (
        StatusAssinatura.TRIAL if plano.trial_dias > 0 else StatusAssinatura.ATIVO
    )

    cliente = Cliente(
        nome=nome_empresa,
        cnpj=cnpj_norm,
        email_contato=contato_norm,
        telefone=telefone,
        plano_id=plano.id,
        status_assinatura=status,
        trial_termina_em=trial_termina_em,
    )
    db.add(cliente)
    await db.flush()  # popular cliente.id pra uso nas FKs

    user = User(
        email=admin_email_norm,
        nome=admin_nome.strip(),
        hashed_password=hash_password(admin_senha),
        role=UserRole.ADMIN,
        ativo=True,
        # Multi-tenancy: vincula user ao cliente recem criado pra que
        # queries (lotes, fichas, beneficiarios) sejam filtradas
        cliente_id=cliente.id,
    )
    db.add(user)
    await db.flush()

    # Asaas best-effort
    if asaas_client.is_configured():
        try:
            resp = await asaas_client.criar_customer(
                nome=cliente.nome,
                cpf_cnpj=cliente.cnpj,
                email=cliente.email_contato or admin_email_norm,
                telefone=cliente.telefone,
                external_reference=str(cliente.id),
            )
            customer_id = resp.get("id")
            if customer_id:
                cliente.asaas_customer_id = str(customer_id)
                await db.flush()
        except (AsaasIndisponivelError, AsaasFalhouError) as exc:
            # Não bloqueia signup. Cliente pode sincronizar depois.
            log.warning(
                "signup.asaas_customer_falhou",
                cliente_id=str(cliente.id),
                erro=exc.message,
            )

    log.info(
        "signup.criado",
        cliente_id=str(cliente.id),
        user_id=str(user.id),
        plano=plano.slug,
        em_trial=trial_termina_em is not None,
    )

    return cliente, user


__all__ = ["signup"]
