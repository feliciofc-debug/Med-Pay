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

    result = await db.execute(select(User).where(User.id == user_id))
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

    COORDENADOR é EXCLUÍDO de propósito — ele só vê o painel dele com
    as fichas que ele subiu. Operador/Aprovador/Admin têm visão geral.
    """
    if current_user.role == UserRole.COORDENADOR:
        raise PermissaoNegadaError(
            "Coordenador não tem acesso à visão executiva. Use seu painel próprio."
        )
    return current_user


__all__ = [
    "get_current_user",
    "get_db",
    "require_admin",
    "require_aprovador",
    "require_pode_subir_ficha",
    "require_visao_executiva",
]
