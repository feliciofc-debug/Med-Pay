"""Rotas de autenticação."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserOut
from app.services.auth import AuthService

router = APIRouter()


def _set_auth_cookie(response: Response, access_token: str) -> None:
    """Define cookie httpOnly com o access_token.

    - HttpOnly: bloqueia acesso via JS (anti-XSS)
    - Secure: só envia em HTTPS (prod)
    - SameSite=none em produção (frontend e backend em domínios diferentes:
      Vercel + Render). SameSite=lax em dev (mesmo domínio localhost).
    """
    samesite_value: str = "none" if settings.is_production else "lax"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite=samesite_value,  # type: ignore[arg-type]
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Autentica usuário e retorna par de tokens.

    Em produção, o `access_token` também é retornado em cookie httpOnly
    para o frontend usar — o JSON é mantido para clientes que preferem
    armazenar manualmente (mobile, SDKs).
    """
    service = AuthService(db)
    user = await service.autenticar(payload.email, payload.password)
    tokens = service.gerar_tokens(user)
    _set_auth_cookie(response, tokens.access_token)
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Troca refresh_token por par novo de tokens."""
    service = AuthService(db)
    tokens = await service.refresh(payload.refresh_token)
    _set_auth_cookie(response, tokens.access_token)
    return tokens


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Limpa o cookie de autenticação."""
    response.delete_cookie(key="access_token", path="/")
    return {"success": True}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Retorna o usuário atualmente autenticado."""
    return current_user
