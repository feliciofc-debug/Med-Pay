"""Serviço de autenticação — login, refresh e criação de usuário."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    CredenciaisInvalidasError,
    TokenExpiradoError,
    TokenInvalidoError,
    UsuarioInativoError,
)
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import TokenPair


class AuthService:
    """Encapsula lógica de autenticação."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def autenticar(self, email: str, password: str) -> User:
        """Valida credenciais e retorna o usuário.

        Raises:
            CredenciaisInvalidasError: email ou senha errados
            UsuarioInativoError: usuário desativado
        """
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.hashed_password):
            # Mensagem genérica — nunca confirmamos se o email existe
            raise CredenciaisInvalidasError("E-mail ou senha incorretos")

        if not user.ativo:
            raise UsuarioInativoError("Usuário desativado — contate o administrador")

        # Atualiza last_login
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()

        return user

    def gerar_tokens(self, user: User) -> TokenPair:
        """Gera par access + refresh tokens para o usuário."""
        access = create_access_token(
            user.id,
            extra_claims={"role": user.role.value, "email": user.email},
        )
        refresh = create_refresh_token(user.id)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Recebe um refresh_token válido e devolve um novo par.

        Raises:
            TokenInvalidoError | TokenExpiradoError
        """
        try:
            payload = decode_token(refresh_token)
        except JWTError as exc:
            msg = str(exc).lower()
            if "expired" in msg:
                raise TokenExpiradoError("Refresh token expirado") from exc
            raise TokenInvalidoError("Refresh token inválido") from exc

        if payload.get("type") != "refresh":
            raise TokenInvalidoError("Token não é do tipo refresh")

        try:
            user_id = UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise TokenInvalidoError("Refresh token malformado") from exc

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.ativo:
            raise TokenInvalidoError("Usuário do token não é mais válido")

        return self.gerar_tokens(user)

    async def criar_usuario(
        self,
        email: str,
        nome: str,
        senha: str,
        role: UserRole = UserRole.OPERADOR,
    ) -> User:
        """Cria um novo usuário (uso interno — script de admin / seed).

        Não exposto via API pública. Para criar admin inicial use
        `app.scripts.create_admin`.
        """
        email_norm = email.lower().strip()
        existing = await self.db.execute(select(User).where(User.email == email_norm))
        if existing.scalar_one_or_none() is not None:
            raise CredenciaisInvalidasError(
                f"Já existe um usuário com email {email_norm}"
            )

        user = User(
            email=email_norm,
            nome=nome.strip(),
            hashed_password=hash_password(senha),
            role=role,
            ativo=True,
        )
        self.db.add(user)
        await self.db.flush()
        return user
