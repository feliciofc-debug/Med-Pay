"""Dependências reutilizáveis para endpoints FastAPI.

Funções aqui são injetadas via `Depends(...)` nas rotas. Centralizar
permite testar mockando uma única função.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import (
    PermissaoNegadaError,
    TokenExpiradoError,
    TokenInvalidoError,
    UsuarioInativoError,
)
from app.core.security import JWTError, decode_token
from app.models.user import User, UserRole

# ============================================================
# Database
# ============================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Sessão do banco — equivalente a `core.database.get_db` (re-export).

    Use em endpoints com `db: AsyncSession = Depends(get_db)`.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================
# Autenticação
# ============================================================

# tokenUrl é só metadata pro Swagger UI — nosso endpoint real é /api/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Recupera usuário autenticado a partir do JWT.

    Aceita o token em duas formas (em ordem de prioridade):
    1. Cookie `access_token` (forma preferida em produção, httpOnly + Secure)
    2. Header `Authorization: Bearer <token>` (fallback / dev)

    Raises:
        TokenInvalidoError: Token ausente, malformado ou assinatura inválida
        TokenExpiradoError: Token expirado
        UsuarioInativoError: Usuário desativado
    """
    raw_token = request.cookies.get("access_token") or token
    if not raw_token:
        raise TokenInvalidoError("Token de autenticação não fornecido")

    try:
        payload = decode_token(raw_token)
    except JWTError as exc:
        msg = str(exc).lower()
        if "expired" in msg or "expirou" in msg:
            raise TokenExpiradoError("Sessão expirada — faça login novamente") from exc
        raise TokenInvalidoError("Token inválido") from exc

    if payload.get("type") != "access":
        raise TokenInvalidoError("Token não é do tipo access")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise TokenInvalidoError("Token sem identificação de usuário")

    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise TokenInvalidoError("Token com identificador malformado") from exc

    # Carrega cliente junto (eager) — usado pelo frontend pra mostrar
    # nome do hospital no menu e pelos guards de tenant.
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.cliente))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise TokenInvalidoError("Usuário do token não existe mais")
    if not user.ativo:
        raise UsuarioInativoError("Usuário desativado — contate o administrador")

    return user


def require_aprovador(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependência que exige usuário com permissão de aprovação.

    Use em endpoints sensíveis (ex: aprovar lote):
        async def aprovar_lote(..., user: User = Depends(require_aprovador)): ...
    """
    if not current_user.pode_aprovar:
        raise PermissaoNegadaError(
            "Apenas usuários com perfil APROVADOR ou ADMIN podem executar esta operação"
        )
    return current_user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependência que exige perfil ADMIN."""
    if current_user.role != UserRole.ADMIN:
        raise PermissaoNegadaError("Apenas usuários ADMIN podem executar esta operação")
    return current_user


def _tenant_executa_pagamento(user: User) -> bool:
    """Tenant do user tem a capacidade 'pagamento.execucao' ligada?

    Checa direto no `features_override` (onde os presets gravam) pra não
    disparar lazy-load de `cliente.plano` no contexto async — o
    `get_current_user` já carrega `user.cliente` com selectinload.
    """
    cliente = user.cliente
    if cliente is None:
        return False
    override = cliente.features_override or {}
    return override.get("pagamento.execucao") is True


def require_execucao_pagamento(
    current_user: User = Depends(get_current_user),
) -> User:
    """Pode executar o ciclo de pagamento (aprovar lote, gerar CNAB / enviar).

    Regra (engenharia de modelos de negócio — ver mapa mental):
        - APROVADOR / ADMIN: sempre (modelo BPO; a MedPag fecha o ciclo do hospital).
        - GESTOR de tenant com `pagamento.execucao` ligada: empresa de repasse e
          MedPag-SCP operam o ciclo completo sozinhas (uma pessoa lança e aprova).

    Hospital comum (sem a feature) segue exigindo Aprovador — separação de poderes.
    """
    if current_user.pode_aprovar:  # APROVADOR ou ADMIN
        return current_user
    if current_user.role == UserRole.GESTOR and _tenant_executa_pagamento(current_user):
        return current_user
    raise PermissaoNegadaError(
        "Seu perfil não pode executar pagamentos neste tenant. "
        "Empresas de repasse precisam da capacidade 'Execução de pagamento' ligada."
    )


def require_pode_subir_ficha(
    current_user: User = Depends(get_current_user),
) -> User:
    """Pode subir ficha/planilha: ADMIN, OPERADOR, APROVADOR e COORDENADOR.

    O COORDENADOR é o ponto de entrada da operação — ele leva as fichas
    do hospital pra plataforma. Demais roles também podem porque cada
    um pode revisar/corrigir o que está em andamento.
    """
    permitidos = {
        UserRole.ADMIN,
        UserRole.APROVADOR,
        UserRole.OPERADOR,
        UserRole.COORDENADOR,
    }
    if current_user.role not in permitidos:
        raise PermissaoNegadaError(
            "Sem permissão pra subir fichas. Contate o administrador."
        )
    return current_user


def require_visao_executiva(
    current_user: User = Depends(get_current_user),
) -> User:
    """Visão executiva (Executivo, Equipe, Erros, Devoluções, Empresa).

    COORDENADOR e MEDICO são EXCLUÍDOS de propósito — eles só veem
    o painel próprio. Operador/Aprovador/Admin/Gestor/Financeiro
    têm visão geral conforme o papel.
    """
    if current_user.role in (UserRole.COORDENADOR, UserRole.MEDICO):
        raise PermissaoNegadaError(
            f"{current_user.role.value} não tem acesso à visão executiva."
        )
    return current_user


def require_medico(
    current_user: User = Depends(get_current_user),
) -> User:
    """Médico (prestador) — usado em endpoints do app do médico.

    Aceita também ADMIN para suporte/diagnóstico (entrar como o
    médico em caso de problema). Recusa outros papéis pra não
    misturar contextos.
    """
    if current_user.role not in (UserRole.MEDICO, UserRole.ADMIN):
        raise PermissaoNegadaError(
            "Esta área é exclusiva do médico (prestador)."
        )
    return current_user


def require_gestor_hospital(
    current_user: User = Depends(get_current_user),
) -> User:
    """Gestor do hospital — aprova fechamento de período, ve relatório
    consolidado. Aceita também ADMIN (MedPag interno) e APROVADOR.
    """
    permitidos = {UserRole.GESTOR, UserRole.ADMIN, UserRole.APROVADOR}
    if current_user.role not in permitidos:
        raise PermissaoNegadaError(
            "Apenas gestores do hospital podem aprovar fechamento."
        )
    return current_user


def require_financeiro(
    current_user: User = Depends(get_current_user),
) -> User:
    """Financeiro do hospital — baixa CNAB e folha de pagamento.

    Aceita ADMIN, APROVADOR e GESTOR também (são quem aprovam, mas
    podem precisar baixar o arquivo em emergências).
    """
    permitidos = {
        UserRole.FINANCEIRO,
        UserRole.GESTOR,
        UserRole.APROVADOR,
        UserRole.ADMIN,
    }
    if current_user.role not in permitidos:
        raise PermissaoNegadaError(
            "Apenas o financeiro do hospital pode baixar CNAB/folha."
        )
    return current_user


# ============================================================
# Multi-tenancy
# ============================================================


def get_tenant_id(
    current_user: User = Depends(get_current_user),
) -> UUID | None:
    """Retorna o `cliente_id` que deve filtrar queries do usuário.

    Convenções:
        - None  → user é "MedPag interno" (admin/operação do BPO), vê
                  dados de todos os tenants
        - UUID  → user pertence a esse cliente, deve ver só os dados dele

    Use em endpoints assim:

        async def listar_lotes(
            tenant_id: UUID | None = Depends(get_tenant_id),
            db: AsyncSession = Depends(get_db),
        ):
            stmt = select(Lote)
            stmt = aplicar_filtro_tenant(stmt, Lote, tenant_id)
            ...

    Quando todos os clientes virarem multi-tenant puro (sem MedPag
    interno), trocar este `get_tenant_id` por `require_tenant_id`
    abaixo.
    """
    return current_user.cliente_id


def require_tenant_id(
    current_user: User = Depends(get_current_user),
) -> UUID:
    """Versão estrita — bloqueia users sem cliente_id (MedPag interno).

    Útil em endpoints que SÓ fazem sentido pra cliente especifico
    (ex: GET /api/operacao do MEU cliente). Em endpoints "globais"
    (Super Admin), use `get_tenant_id` (que aceita None).
    """
    if current_user.cliente_id is None:
        raise PermissaoNegadaError(
            "Este endpoint requer usuário vinculado a um cliente. "
            "Users MedPag internos devem usar os endpoints administrativos."
        )
    return current_user.cliente_id


def require_feature(chave: str):  # noqa: ANN201
    """Factory de dependency que exige feature ativa pro cliente do user.

    Uso típico:

        @router.post(
            "/lotes/{lote_id}/cnab",
            dependencies=[Depends(require_feature("pagamento.cnab"))],
        )
        async def gerar_cnab(...): ...

    Regras:
        - User MedPag interno (cliente_id is None): sempre passa
          (acesso total — útil pra debug/suporte)
        - User vinculado a cliente: feature precisa estar ativada
          (no plano OU no `features_override` do cliente)

    Levanta 403 PERMISSAO_NEGADA se a feature está desligada.
    """

    async def _checar(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if current_user.cliente_id is None:
            return  # MedPag interno passa direto

        from app.models.cliente import Cliente
        from app.services.feature_flags import cliente_tem_feature

        result = await db.execute(
            select(Cliente).where(Cliente.id == current_user.cliente_id)
        )
        cliente = result.scalar_one_or_none()
        if cliente is None:
            raise PermissaoNegadaError(
                "Cliente do usuário não encontrado — sessão inválida."
            )
        if not cliente_tem_feature(cliente, chave):
            raise PermissaoNegadaError(
                f"Funcionalidade '{chave}' não está disponível no seu plano. "
                "Contate o suporte pra ativar."
            )

    return _checar


def verificar_acesso_cliente(
    user: User, cliente_id_alvo: UUID, *, mensagem: str | None = None
) -> None:
    """Garante que `user` pode acessar dados do cliente `cliente_id_alvo`.

    Regra:
        - MedPag interno (user.cliente_id is None) → sempre pode
        - Caso contrário, user.cliente_id deve igualar cliente_id_alvo

    Use em endpoints onde o cliente_id vem do path/query e precisa
    validar contra o tenant do user:

        @router.get("/{cliente_id}/relatorio")
        async def relatorio(
            cliente_id: UUID,
            user: User = Depends(get_current_user),
        ):
            verificar_acesso_cliente(user, cliente_id)
            ...
    """
    if user.cliente_id is None:
        return  # MedPag interno
    if user.cliente_id != cliente_id_alvo:
        raise PermissaoNegadaError(
            mensagem
            or "Você não tem acesso a dados de outro cliente.",
        )


__all__ = [
    "get_current_user",
    "get_db",
    "get_tenant_id",
    "require_admin",
    "require_aprovador",
    "require_execucao_pagamento",
    "require_feature",
    "require_pode_subir_ficha",
    "require_tenant_id",
    "require_visao_executiva",
    "verificar_acesso_cliente",
]
